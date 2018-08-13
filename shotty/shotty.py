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

# has_pending_snapshot
# Encapsulates check to see if there is a pending snapshots
# Inputs:
#   volume - The volume to checking
# Returns
#   True - There are snapshots pending for this volumes
#   False - There are no snapshots pending for this volume
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

# can_process_command
# For instance stop, start, snapshot and reboot commands, do not execute
# command without a --project parameter unless the --force option is specified
# Inputs:
#   command - the command requested. Only certain cammands require force, keep
#       everything in this block
#   project - parameter passed for specifying a project tag Value
#   force - parameter passed for the --force command, required if no project
#       param passed
#   profile - Which profile. A profile of Kyle will disable force restrictions
# Returns
#   True - The requested instances command can be executed
#   False - The force command is required to execute, do not execute
def can_process_command(command, project, force, profile):
    can_process = False # variable to identify if the command can be executed, init to False

    # check to see if the command being applied is in the list that has a force restriction
    if (command in aws_commands):
        # if there is no project tag specified and no force tag, we cannot execute
        # if the profile is Kyle, force logic is disabled
        if ((not project) and (not force)) and (profile != 'Kyle'):
            # print("Cannot execute this command without --force since --project is not set")
            can_process = False
        else:
            can_process = True
    else: # if not in the list of commands that have a force restriction, then it is ok
        can_process = True

    return can_process

# execute_instance_command
# Centralize execution of instance commands for stop, start, reboot
# The logic between these is virtually identical except for the command and messaage
# This function will help ensure all three are in synch
# See instances snapshot as that has separate logic so is not included here
# Inputs
#   command - The command we are executing (see aws_commands for valid values)
#   project - Project tag value to filter on (if present)
#   force - If the --force value was passed, required if no project value specified (depenedent on profile)
#   profile - Profile Kyle will disable force restrictions
#   command_executing_desc - Text for action description (Starting, Stopping, Rebooting)
# Returns:
#   Nothing
def execute_instance_command(command, project, force, profile, command_executing_desc):
    # check if the command requires --force if no project tag was specified (or profile disables)
    if (not can_process_command(command, project, force, profile)):
        print("Cannot execute instances {0} without --force since --project is not set".format(command))
        print("Alternately --profile=Kyle will disable --force restrictions")
    else:
        instances = filter_instances(project)

        for i in instances:
            print("{0} {1}...".format(command_executing_desc, i.id))
            try:
                # reboot instance
                if (command == 'reboot'):
                    i.reboot()
                # stop the instance
                elif (command == 'stop'):
                    i.stop()
                # start the instanc
                elif (command == 'start'):
                    i.start()
                else:
                    # if we got here then the value passed was not what we expected and code fix is needed
                    # note snapshot command has different logic and is covered in a separate function
                    raise ValueError("Value Error: command passed to execute_instance_command must be in {0}".format(aws_commands))

            # cover exceptions
            except botocore.exceptions.ClientError as e:
                print("Could not {0} {1}: ".format(command, i.id) + str(e))
                continue

    return

@click.group()
def cli():
    """Shotty manages snapshots"""

@cli.group('snapshots')
def snapshots():
    """Commands for snapshots"""

# Snapshots list command
@snapshots.command('list')
@click.option('--project', default=None,
    help="Only snapshots for project (tag Project:<name>)")
@click.option('--all', 'list_all', default=False, is_flag=True,
    help="List all snapshots for each volume, not just the most recent one")
def list_snapshots(project, list_all):
    "List EC2 snapshots"

    # Filter instance list to look for snapshots by project tag references if present
    instances = filter_instances(project)

    # For all in scope instances
    for i in instances:
        # Look at all volumes for the selected instance
        for v in i.volumes.all():
            # Iterate through all snapshots for the volume
            for s in v.snapshots.all():
                print(", ".join((
                    s.id, # snapshot ID
                    v.id, # Volume ID
                    i.id, # Instance ID
                    s.state, # state of the snapshot
                    s.progress, # Progress of the snapshot
                    s.start_time.strftime("%c") # when the snapshot was started
                    )))

                if s.state == 'completed' and not list_all: break

    return

@cli.group('volumes')
def volumes():
    """Commands for volumes"""

# Volumes list command
@volumes.command('list')
@click.option('--project', default=None,
    help="Only volumes for project (tag Project:<name>)")
def list_volumes(project):
    "List EC2 volumes"

    # Filter instances based on project tags, if present
    instances = filter_instances(project)

    # For all selected instances
    for i in instances:
        # Iterate through all volumes for the instance
        for v in i.volumes.all():
            print(", ".join((
                v.id, # volume ID
                i.id, # instance ID
                v.state, # volume state
                str(v.size) + "GiB", # size of volume
                v.encrypted and "Encrypted" or "Not Encrypted"
                )))

    return

@cli.group('instances')
def instances():
    """Commands for instances"""

# Instances snapshot command
@instances.command('snapshot',
    help="Create snapshots of all volumes")
@click.option('--project', default=None,
    help="Only instances for project (tag Project:<name>)")
@click.option('--force', 'force', default=False, is_flag=True,
    help="Force operation if the --project param was not specified.")
@click.option('--profile', 'profile', default=None,
    help="Specify a profile to use. Profile Kyle will avoid force restriction")
def create_snapshots(project, force, profile):
    "Create snapshots for EC2 intances"

    # the snapshot command requires --force if no project tag was specified
    if (not can_process_command('snapshot', project, force, profile)):
        print("Cannot execute this command without --force since --project is not set")
    else:
        # We can proceed and try to execute the snapshot
        instances = filter_instances(project) # only operate on project tagged instances if passed
        # For each of the filtered instances (or all if the filter had no effect)
        for i in instances:
            instance_was_running = (i.state['Name'] == 'running')
            print("Instance {0} was in this state: {1}".format(i.id, i.state['Name']))
            # Notify the user which instance we are stopping
            print("Stopping {0}...".format(i.id))
            try:
                # stop the instance prior to starting the snapshot
                i.stop()
                i.wait_until_stopped()
            # catch execptions if there was an issue
            except botocore.exceptions.ClientError as e:
                print("Could not stop {0}: ".format(i.id) + str(e))
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
                try:
                    v.create_snapshot(Description="Created by SnapshotAlyzer 30000")
                # catch exceptions
                except botocore.exceptions.ClientError as e:
                    print("Could not create snapshot for {0}:".format(v.id) + str(e))
                    continue

            # Snapshot was started, notify the user and restart the instance
            # only start the instance if it was running originally
            if (instance_was_running):
                print("Instance {0} was running previously, restarting...".format(i.id))
                i.start() # start the instance
                i.wait_until_running() # wait for the instance to start before moving on
            else:
                print("Instance {0} was not running originally so is not restarted".format(i.id))

        print("Job's done!")

    return

# Instances list command
@instances.command('list')
@click.option('--project', default=None,
    help="Only instances for project (tag Project:<name>)")
def list_instances(project):
    "List EC2 instances"

    # Filter instances based on Project tag, if present
    instances = filter_instances(project)

    # Iterate through all filtered instances
    for i in instances:
            # pull tag values for the instance
            tags = { t['Key']: t['Value'] for t in i.tags or [] }
            print(', '.join((
            i.id, # instance ID
            i.instance_type, # instance type
            i.placement['AvailabilityZone'], # instance availability zone
            i.state['Name'], # current instance state
            i.public_dns_name, # public dns name for instance
            tags.get('Project', '<no project>')))) # Project tag if present

    return

# Instances stop command
@instances.command('stop')
@click.option('--project', default=None,
    help='Only instances for project')
@click.option('--force', 'force', default=False, is_flag=True,
    help="Force operation if the --project param was not specified.")
@click.option('--profile', 'profile', default=None,
    help="Specify a profile to use. Profile Kyle will avoid force restriction")
def stop_instances(project, force, profile):
    "Stop EC2 instances"

    # Verify we can execute the command and if so, execute
    execute_instance_command('stop', project, force, profile, 'Stopping')

    return

# Instances start command
@instances.command('start')
@click.option('--project', default=None,
    help='Only instances for project')
@click.option('--force', 'force', default=False, is_flag=True,
    help="Force operation if the --project param was not specified.")
@click.option('--profile', 'profile', default=None,
    help="Specify a profile to use. Profile Kyle will avoid force restriction")
def start_instances(project, force, profile):
    "Start EC2 instances"

    # Verify we can execute the command and if so, execute
    execute_instance_command('start', project, force, profile, 'Starting')

    return

# Instance reboot command
@instances.command('reboot')
@click.option('--project', default=None,
    help='Only instances for project')
@click.option('--force', 'force', default=False, is_flag=True,
    help="Force operation if the --project param was not specified.")
@click.option('--profile', 'profile', default=None,
    help="Specify a profile to use. Profile Kyle will avoid force restriction")
def reboot_instances(project, force, profile):
    "Reboot EC2 instances"

    # Verify we can execute the command and if so, execute
    execute_instance_command('reboot', project, force, profile, 'Rebooting')

    return

if __name__ == '__main__':
    cli()
