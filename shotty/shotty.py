import boto3
import botocore
import click
from enum import Enum

# Tuple for commands. Used for logic to ensure --force command is used when
# no --project value is passed. Only in use for instances commands
aws_commands = ('stop','start','snapshot','reboot')

session = boto3.Session(profile_name='shotty')
ec2 = session.resource('ec2')

# filter_instances
# Filters ec2 instances based on project value (which ties to Project tag) or all
# if no project value is passed
# Inputs
#   project = The project name to filter Project tags by
# Returns
#   A list of filtered instances
def filter_instances(project):
    instances = []

    if project:
        filters = [{'Name':'tag:Project','Values':[project]}]
        instances = ec2.instances.filter(Filters=filters)
    else:
        instances = ec2.instances.all()

    return instances

def has_pending_snapshot(volume):
    snapshots = list(volume.snapshots.all())
    return snapshots and snapshots[0].state == 'pending'

# get_project_name
# For the passed instance value, determine the value of the Project tag for that
# ec2 instances
# Inputs
#   instance - The instance we are checking the tag for
# Returns
#   The tag name if present, None if not
def get_project_name(instance):
    tagval = None

    # iterate through the instances tags to find Project
    for tags in ec2instance.tags:
        if tags["Key"] == 'Project':
            tagval = tags["Value"]
            print("The project is {0}...".format(tagval))
            break
        else: # if not the Project tag, keep iterating
            continue

    return tagval

# For instance stop, start, snapshot and reboot commands, do not execute
# command without a --project parameter unless the --force option is specified
# Inputs:
#   command - the command requested. Only certain cammands require force, keep
#       everything in this block
#   project - parameter passed for specifying a project tag Value
#   force - parameter passed for the --force command, required if no project
#       param passed
# Returns
#   True - The requested instances command can be executed
#   False - The force command is required to execute, do not execute
def can_process_command(command, project, force):
    can_process = False # variable to identify if the command can be executed, init to False

    # check to see if the command being applied is in the list that has a force restriction
    if (command in aws_commands):
        # if there is no project tag specified and no force tag, we cannot execute
        if (not project) and (not force):
            # print("Cannot execute this command without --force since --project is not set")
            can_process = False
        else:
            can_process = True
    else: # if not in the list of commands that have a force restriction, then it is ok
        can_process = True

    return can_process

@click.group()
def cli():
    """Shotty manages snapshots"""
@cli.group('snapshots')
def snapshots():
    """Commands for snapshots"""
@snapshots.command('list')
@click.option('--project', default=None,
    help="Only snapshots for project (tag Project:<name>)")
@click.option('--all', 'list_all', default=False, is_flag=True,
    help="List all snapshots for each volume, not just the most recent one")
def list_snapshots(project, list_all):
    "List EC2 snapshots"

    instances = filter_instances(project)
    for i in instances:
        tagname = get_project_name(i)
        if tagname:
            print("The project name was: {0}.".format(tagname))
        else:
            print("There was no project for this one: {0}".format(i))

        for v in i.volumes.all():
            for s in v.snapshots.all():
                print(", ".join((
                    s.id,
                    v.id,
                    i.id,
                    s.state,
                    s.progress,
                    s.start_time.strftime("%c")
                    )))

                if s.state == 'completed' and not list_all: break

    return

@cli.group('volumes')
def volumes():
    """Commands for volumes"""
@volumes.command('list')
@click.option('--project', default=None,
    help="Only volumes for project (tag Project:<name>)")
def list_volumes(project):
    "List EC2 volumes"

    instances = filter_instances(project)
    for i in instances:
        for v in i.volumes.all():
            print(", ".join((
                v.id,
                i.id,
                v.state,
                str(v.size) + "GiB",
                v.encrypted and "Encrypted" or "Not Encrypted"
                )))

    return

@cli.group('instances')
def instances():
    """Commands for instances"""

@instances.command('snapshot',
    help="Create snapshots of all volumes")
@click.option('--project', default=None,
    help="Only instances for project (tag Project:<name>)")
@click.option('--force', 'force', default=False, is_flag=True,
    help="Force operation if the --project param was not specified.")
def create_snapshots(project, force):
    "Create snapshots for EC2 intances"

    # the snapshot command requires --force if no project tag was specified
    if (not can_process_command('snapshot', project, force)):
        print("Cannot execute this command without --force since --project is not set")
    else:
        # We can proceed and try to execute the snapshot
        instances = filter_instances(project) # only operate on project tagged instances if passed
        # For each of the filtered instances (or all if the filter had no effect)
        for i in instances:
            # Notify the user which instance we are stopping
            print("Stopping {0}...".format(i.id))
            try:
                # stop the instance prior to starting the snapshot
                i.stop()
                i.wait_until_stopped()
            # catch execptions if there was an issue (stopped, etc)
            except botocore.exceptions.ClientError as e:
                print("Could not stop {0}. ".format(i.id) + str(e))
                continue

            # For each volume in the current instance
            for v in i.volumes.all():
                # if a snapshot has already been requested or in progress, don't bother
                if has_pending_snapshot(v):
                    # notify the user the decision that was made and a new snapshot will not be made
                    print("  Skipping {0}, snapshot already in progress")
                    continue

                # All was well, create the snapshot. Leave reference that the snapshots
                # came from this utility
                print("Creating snapshot of {0}".format(v.id))
                v.create_snapshot(Description="Created by SnapshotAlyzer 30000")

            # Snapshot was started, notify the user and restart the instance
            print("Starting {0}...".format(i.id))
            # TODO: Add exception handling
            i.start()
            i.wait_until_running()
        print("Job's done!")

    return

@instances.command('list')
@click.option('--project', default=None,
    help="Only instances for project (tag Project:<name>)")
def list_instances(project):
    "List EC2 instances"

    instances = filter_instances(project)

    for i in instances:
            tags = { t['Key']: t['Value'] for t in i.tags or [] }
            print(', '.join((
            i.id,
            i.instance_type,
            i.placement['AvailabilityZone'],
            i.state['Name'],
            i.public_dns_name,
            tags.get('Project', '<no project>'))))

    return

@instances.command('stop')
@click.option('--project', default=None,
    help='Only instances for project')
@click.option('--force', 'force', default=False, is_flag=True,
    help="Force operation if the --project param was not specified.")
def stop_instances(project, force):
    "Stop EC2 instances"

    instances = filter_instances(project)
    for i in instances:
        print("Stopping {0}...".format(i.id))
        if (can_process_command('stop', project, force)):
            try:
                i.stop()
            except botocore.exceptions.ClientError as e:
                print("Could not stop {0}. ".format(i.id) + str(e))
                continue
        else:
            print("Cannot execute this command without --force since --project is not set")

    return

@instances.command('start')
@click.option('--project', default=None,
    help='Only instances for project')
@click.option('--force', 'force', default=False, is_flag=True,
    help="Force operation if the --project param was not specified.")
def stop_instances(project, force):
    "Start EC2 instances"

    instances = filter_instances(project)
    for i in instances:
        print("Starting {0}...".format(i.id))
        if (can_process_command('start', project, force)):
            try:
                i.start()
            except botocore.exceptions.ClientError as e:
                print("Could not start {0}. ".format(i.id) + str(e))
                continue
        else:
            print("Cannot execute this command without --force since --project is not set")

    return

@instances.command('reboot')
@click.option('--project', default=None,
    help='Only instances for project')
@click.option('--force', 'force', default=False, is_flag=True,
    help="Force operation if the --project param was not specified.")
def reboot_instances(project, force):
    "Reboot EC2 instances"

    instances = filter_instances(project)
    for i in instances:
        print("Rebooting {0}...".format(i.id))
        if (can_process_command('reboot', project, force)):
            try:
                i.reboot()
            except botocore.exceptions.ClientError as e:
                print("Could not reboot {0}. ".format(i.id) + str(e))
                continue
        else:
            print("Cannot execute this command without --force since --project is not set")

    return

if __name__ == '__main__':
    cli()
