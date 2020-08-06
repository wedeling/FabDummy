# FabSim3 Commands Python API
#
# This file maps command-line instructions for FabSim3 to Python functions.
# NOTE: No effort is made to map output back to FabSim, as this complicates
# the implementation greatly.
#
# This file can be included in any code base. 
# It has no dependencies, but does require a working FabSim3 installation.

import os
import time
import subprocess
from base.fab import *

add_local_paths("FabUQCampaign")

def fabsim(command, arguments, machine = 'localhost'):
    """
    Generic function for running any FabSim3 command.

    Parameters
    ----------
    - command (string): the FanSim3 command to execute
    - arguments (string): a list of arguments, starting with the config ID,
      followed by keyword arguments "config,arg1=....,arg2=...."
    - machine (string): the name of the remote machine as indicated in
      machines_user.yml

    Returns
    -------
    None
    """
    print('Executing', "fab {} {}:{}".format(machine, command, arguments))
    os.system("fabsim {} {}:{}".format(machine, command, arguments))

def fetch_results(machine='localhost'):
    """
    Retrieves the results from the remote machine, and stores it in the FabSim3
    results directory.

    Parameters
    ----------
    - machine (string): the name of the remote machine as indicated in
      machines_user.yml

    Returns
    -------
    Boolean flag, indicating success (True) or failure (False)

    """
    #Q: will this catch errors in fetch_results??
    try:
        fabsim("fetch_results", "", machine)
        return True
    except:
        return False
    
def status(machine='localhost'):
    """
    Prints the status of the jobs running on the remote machine.

    Parameters
    ----------
    - machine (string): the name of the remote machine as indicated in
      machines_user.yml

    Returns
    -------
    None

    """
    fabsim("stat", "", machine)
    
def wait(machine='localhost', sleep=1):
    """
    Subroutine which returns when all jobs on the remote machine have finished.
    Checks the status of the jobs every <sleep> minutes. The method works in
    the same way a human would, by examining the output of fab <machine> stat.

    Parameters
    ----------
    - machine (string): the name of the remote machine as indicated in
      machines_user.yml
    - sleep (int, default=1): time interval in minutes between checks

    Returns
    -------
    finished (boolean) : if False, something went wrong

    """
    #number of header lines in fab <machine> stat
    header = 2
    finished = False

    while not finished:
        #get the output lines of fab <machine> stat
        try:
            out = subprocess.run(['fab', machine, 'stat'], stdout=subprocess.PIPE)
        except:
            print('wait subroutine failed')
            return finished

        out = out.stdout.decode('utf-8').split("\n")
        #number of uncompleted runs
        n_uncompleted = 0
        print('Checking job status...')
        for i in range(header, len(out)):
            #remove all spaces from current line
            line = out[i].split()

            #line = '' means no Job ID, and if the number of uncompleted runs
            #is zero, we are done
            if len(line) == 0 and n_uncompleted == 0:
                print('All runs have completed')
                finished = True
                return finished
            #If the first entry is a number, we have found a running/pending or
            #completing job ID
            elif len(line) > 0 and line[0].isnumeric():
                print('Job %s is %s' % (line[0], line[1]))
                n_uncompleted += 1

        #no more jobs
        if n_uncompleted == 0:
            finished = True
            return finished
        #still active jobs, sleep
        else:
            time.sleep(sleep * 60)

def verify_last_ensemble(config, campaign_dir, target_filename, machine):
    """
    Execute the FamSim3 command with the same name. Checks if the output file 
    <target_filename> for each run in the SWEEP directory is present in 
    the corresponding FabSim3 results directory.

    Parameters
    ----------
    - config (string): the config ID, i.e. the name in <fab_fome>/config_files/<config>
    - campaign_dir (string): the EasyVVUQ work directory
    - target_filename (string): the name of the filename to check the existence of.
      (strored in campaign._active_decoder.target_filename)
    - machine (string): the name of the remote machine as indicated in
      machines_user.yml

    Returns
    -------
    all_good (boolean): True if all output files are present, False otherwise.

    """

    fetch_good = fetch_results(machine=machine)
    n_fetch = 1; max_fetch = 10
    #if an exception occured in fetch_results, try max_fetch times at most
    if not fetch_good:
        fetch_good = fetch_results(machine=machine)
        n_fetch += 1
        if n_fetch > max_fetch and not fetch_good:
            print('Error in fetching results after trying %d times' % max_fetch)
            import sys; sys.exit()

    #filename might contain '=', which fabsim interprets as an argument
    target_filename = target_filename.replace('=', 'replace_equal')

    #Run FabSim3 verify_last_ensemble command
    arguments = "{},campaign_dir={},target_filename={}".format(config, 
                                                               campaign_dir, 
                                                               target_filename)

    fabsim("verify_last_ensemble", arguments, machine='localhost')
    #FabSim3 verify_last_ensemble command writes a flag to the check.dat file
    #in the EasuVVUQ work dir. Read to see if all files were present.
    fp = open(os.path.join(campaign_dir, 'check.dat'), 'r')
    all_good = bool(int(fp.read()))
    fp.close()
    return all_good

def verify(config, campaign_dir, target_filename, machine, max_resubmit=2, 
           max_wait=10, PilotJob=False):
    """
    This will execute the verify_last_ensemble subroutine to see if the output file 
    <target_filename> for each run in the SWEEP directory is present in 
    the corresponding FabSim3 results directory. If this is not the case, the 
    (entire) previous ensemble will be executed again. An "ensemble" is 
    defined here as any run present in the SWEEP directory. In the case of 
    the dimension-adaptive sampler, this will be only the runs of the previous 
    iteration.

    Then, it checks for the presence of the output file once more. 
    This cycle repeats for a user-specified maximum number of times.

    Parameters
    ----------
    - config (string) : the config ID, i.e. the name in <fab_fome>/config_files/<config>
    - campaign_dir (string) : the EasyVVUQ work directory
    - target_filename (string): the name of the filename to check the existence of.
      (strored in campaign._active_decoder.target_filename)
    - machine (string) : the name of the remote machine as indicated in
      machines_user.yml
    - max_resubmit (int, default=2) : the maximum number of times an 
      ensemble can be executed again if it failed. If this number is exceeded 
      the sampling will terminate.
    - PilotJob (boolean): Use the QCG PilotJob framework to execute the ensemble.
      Must be installed. If False, jobs are execute via the Slurm workload manager.

    Returns
    -------
    None.

    """

    #wait for all jobs to finish
    finished = wait(machine=machine)

    #sometimes the wait subroutine fails, e.g. due to some ssh connection issue,
    #retry max_wait times at most
    n_wait = 1
    while not finished:
        print("Wait subroutine failed, executing again")
        finished = wait(machine=machine)
        n_wait += 1
        if n_wait > max_wait and finished == False:
            print('fabsim3_cmd_api.wait failed %d times, exiting.' % max_wait)
            import sys; sys.exit()

    #check if the last ensemble returned all output files
    all_good = verify_last_ensemble(config, campaign_dir, 
                                    target_filename, machine=machine)

    n_retry = 0
    while not all_good and n_retry < max_resubmit:
        resubmit_previous_ensemble(config, machine=machine, PilotJob=PilotJob)
        wait(machine=machine)
        #check if the last ensemble returned all output files
        all_good = verify_last_ensemble(config, campaign_dir, 
                                        target_filename, machine=machine)
        if all_good: break
        n_retry += 1

    if not all_good:
        print('Unsuccesfull ensemble after resubmitting %d times.' % max_resubmit)
        import sys; sys.exit()   

def resubmit_previous_ensemble(config, script, command='uq_ensemble',
                               machine='localhost', PilotJob=False):
    """
    Resubmits all jobs in the SWEEP directory: <fab_home>/config_files/<config>/SWEEP

    Parameters
    ----------
    - config (string): the config ID, i.e. the name in <fab_fome>/config_files/<config>
    - script (string): the FabSim3 script to execute
    - command : The default is 'uq_ensemble'.
    - machine (string): the name of the remote machine as indicated in
      machines_user.yml
    - PilotJob (boolean): Use the QCG PilotJob framework to execute the ensemble.
      Must be installed. If False, jobs are execute via the Slurm workload manager.

    Returns
    -------
    None.

    """
    arguments = "{},script={},PilotJob={}".format(config, script, PilotJob)
    fabsim(command, arguments, machine)

def run_uq_ensemble(config, campaign_dir, script, machine='localhost', skip=0,
                    PilotJob = False, **args):
    """
    Launches a EasyVVUQ UQ ensemble

    Parameters
    ----------
    - config (string): the config ID, i.e. the name in <fab_fome>/config_files/<config>
    - campaign_dir (string): the EasyVVUQ work directory
    - script (string): the FabSim3 script to execute
    - machine (string): the name of the remote machine as indicated in
      machines_user.yml
    - skip (int): if > 0, the first <skip> runs are not executed. Required in
      an adaptive setting to avoid recomputing already executed runs.
    - PilotJob (boolean): Use the QCG PilotJob framework to execute the ensemble.
      Must be installed. If False, jobs are execute via the Slurm workload manager.
    
    Returns
    -------
    None

    """
    # sim_ID = campaign_dir.split('/')[-1]
    arguments = "{},campaign_dir={},script={},skip={},PilotJob={}".format(config, campaign_dir, script, skip, PilotJob)
    fabsim("run_uq_ensemble", arguments, machine=machine)
    
def get_uq_samples(config, campaign_dir, number_of_samples, skip=0, machine = 'localhost'):
    """
    Retrieves results from UQ ensemble
    """
    # sim_ID = campaign_dir.split('/')[-1]
    arguments = "{},campaign_dir={},skip={}".format(config, campaign_dir, skip)
    fabsim("get_uq_samples", arguments, machine=machine)
    
    #If the same FabSim3 config name was used before, the statement above
    #might have copied more runs than currently are used by EasyVVUQ.
    #This removes all runs in the EasyVVUQ campaign dir (not the Fabsim results dir) 
    #for which Run_X with X > number of current samples.
    dirs = os.listdir(os.path.join(campaign_dir, 'runs'))
    for dir_i in dirs:
        run_ID = int(dir_i.split('_')[-1])
        if run_ID > number_of_samples:
            local('rm -r %s/runs/Run_%d' % (campaign_dir, run_ID))
            print('Removing Run %d from %s/runs' % (run_ID, campaign_dir))
