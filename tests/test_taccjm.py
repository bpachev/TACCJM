"""
Tests for TACC JobManager Class


Note:


References:

"""
import os
import pdb
import pytest
from dotenv import load_dotenv
from unittest.mock import patch

from taccjm.TACCJobManager import TACCJobManager

__author__ = "Carlos del-Castillo-Negrete"
__copyright__ = "Carlos del-Castillo-Negrete"
__license__ = "MIT"

# Note: .env file in tests directory must contain TACC_USER and TACC_PW variables defined
load_dotenv()

global SYSTEM, USER, PW, SYSTEM, ALLOCATION
USER = os.environ.get("TACCJM_USER")
PW = os.environ.get("TACCJM_PW")
SYSTEM = os.environ.get("TACCJM_SYSTEM")
ALLOCATION = os.environ.get("TACCJM_ALLOCATION")

# JM will be the job manager instance that should be initialized once but used by all tests.
# Note the test_init test initializes the JM to begin with, but if only running one other test,
# the first test to run will initialize the JM for the test session.
global JM
JM = None


def _check_init(mfa):
    global JM
    if JM is None:
        # Initialize taccjm that will be used for tests - use special tests dir
        JM = TACCJobManager(SYSTEM, user=USER, psw=PW, mfa=mfa, apps_dir="test-taccjm-apps",
                jobs_dir="test-taccjm-jobs", trash_dir="test-taccjm-trash")


def test_init(mfa):
    """Testing initializing systems"""

    global JM
    # Initialize taccjm that will be used for tests - use special tests dir
    JM = TACCJobManager(SYSTEM, user=USER, psw=PW, mfa=mfa, apps_dir="test-taccjm-apps",
            jobs_dir="test-taccjm-jobs")

    with pytest.raises(Exception):
        bad = TACCJobManager("foo", user=USER, psw=PW, mfa=mfa)

    # Command that should work, also test printing to stdout the output 
    assert JM._execute_command('echo test', prnt=True) == 'test\n'

    # Tests command that fails
    with pytest.raises(Exception):
         JM._execute_command('foo')

    # Test show queue and get allocation
    assert f"SUMMARY OF JOBS FOR USER: <{USER}>" in JM.showq()
    assert f"Project balances for user {USER}" in JM.get_allocations()


def test_files(mfa):
    """Test listing, sending, and getting files and directories"""
    global JM

    _check_init(mfa)

    # List files in path that exists and doesnt exist
    assert 'test-taccjm-apps' in JM.list_files()
    with pytest.raises(FileNotFoundError):
         JM.list_files('/bad/path')

    # Send file - Try sending test application script to apps directory
    test_file = '/'.join([JM.apps_dir, 'test_file'])
    assert 'test_file' in JM.send_file('./tests/test_app/assets/run.sh',
            test_file)

    # Test peaking at a file just sent
    first = '#### BEGIN SCRIPT LOGIC'
    first_line = JM.peak_file(test_file, head=1)
    assert first in first_line
    last = '${command} ${command_opts} >>out.txt 2>&1'
    last_line = JM.peak_file(test_file, tail=1)
    assert last in last_line
    both_lines = JM.peak_file(test_file)

    with pytest.raises(Exception):
         JM.peak_file('/bad/path')

    # Send directory - Now try sending whole assets directory
    test_folder = '/'.join([JM.apps_dir, 'test_folder'])
    assert 'test_folder' in JM.send_file('./tests/test_app/assets',
            '/'.join([JM.apps_dir, 'test_folder']))
    assert '.hidden_file' not in JM.list_files(path=test_folder)

    # Send directory - Now try sending whole assets directory, include hidden files
    test_folder_hidden = '/'.join([JM.apps_dir, 'test_folder_hidden'])
    assert 'test_folder_hidden' in JM.send_file('./tests/test_app/assets',
            '/'.join([JM.apps_dir, 'test_folder_hidden']), exclude_hidden=False)
    assert '.hidden_file' in JM.list_files(path='/'.join([JM.apps_dir, 'test_folder_hidden']))

    # Get test file
    JM.get_file(test_file, './tests/test_file')
    assert os.path.isfile('./tests/test_file')
    os.remove('./tests/test_file')

    # Get test folder
    JM.get_file(test_folder, './tests/test_folder')
    assert os.path.isdir('./tests/test_folder')
    assert os.path.isfile('./tests/test_folder/run.sh')
    os.system('rm -rf ./tests/test_folder')


def test_templating(mfa):
    """Test loading project configuration files and templating json files"""
    global JM
    _check_init(mfa)

    proj_conf = JM.load_project_config('./tests/test_app/project.ini')
    assert proj_conf['app']['name']=='test_app'
    assert proj_conf['app']['version']=='1.0.0'
    with pytest.raises(FileNotFoundError):
        JM.load_project_config('./tests/test_app/does_not_exist.ini')

    app_config = JM.load_templated_json_file('./tests/test_app/app.json', proj_conf)
    assert app_config['name']=='test_app--1.0.0'
    with pytest.raises(FileNotFoundError):
        JM.load_templated_json_file('./tests/test_app/not_found.json', proj_conf)


def test_deploy_app(mfa):
    """Test deploy applications """
    global JM
    _check_init(mfa)

    # Test deploying app when sending files to system is failing
    with patch.object(TACCJobManager, 'send_file', side_effect=Exception('Mock file send error')):
        with pytest.raises(Exception) as e:
            bad_deploy = JM.deploy_app(local_app_dir='./tests/test_app', overwrite=True)
    # Test deploying app with bad config (missing required config)
    with pytest.raises(Exception) as e:
        bad_deploy = JM.deploy_app(local_app_dir='./tests/test_app', app_config_file='app_2.json',
                overwrite=True)

    # Deploy app (should not exist to begin with)
    test_app = JM.deploy_app(local_app_dir='./tests/test_app', overwrite=True)
    assert test_app['name']=='test_app--1.0.0'

    # Now try without overwrite and this will fail
    with pytest.raises(Exception):
        test_app = JM.deploy_app(local_app_dir='./tests/test_app')

    # Get the wrapper script
    wrapper_script = JM.get_app_wrapper_script(test_app['name'])
    assert "${command} ${command_opts} >>out.txt 2>&1" in wrapper_script

    # Get wrapper script for bad app
    with pytest.raises(FileNotFoundError) as e:
        wrapper_script = JM.get_app_wrapper_script('bad_app')

    # Load the app config, it should match
    loaded_config = JM.load_app_config(test_app['name'])
    assert loaded_config==test_app
    with pytest.raises(Exception):
        JM.load_app_config('does_not_exist')


def test_jobs(mfa):
    """Test setting up a job."""
    global JM
    _check_init(mfa)

    # Make sure app is deployed
    test_app = JM.deploy_app(local_app_dir='./tests/test_app', overwrite=True)

    # Now try setting up test job, but don't stage inputs
    test_config = JM.setup_job(local_job_dir='./tests/test_app',
            job_config_file='job.json', stage=False)
    assert test_config['appId']=='test_app--1.0.0'
    assert 'job_id' not in test_config.keys()

    # Now try setting up test job
    job_config = JM.setup_job(local_job_dir='./tests/test_app', job_config_file='job.json')
    assert job_config['appId']=='test_app--1.0.0'

    # Get job we se just set up
    jobs = JM.get_jobs()
    assert job_config['job_id'] in jobs

    # Fail setting up job -> Mock stage_job to fail
    with patch.object(TACCJobManager, 'stage_job',
            side_effect=Exception('Mock stage_job error')):
        with pytest.raises(Exception) as e:
            job_config = JM.setup_job(local_job_dir='./tests/test_app', job_config_file='job.json')
    # Fail setting up job -> Sending input file fails
    with patch.object(TACCJobManager, 'send_file',
            side_effect=Exception('Mock send_file error')):
        with pytest.raises(Exception) as e:
            job_config = JM.setup_job(local_job_dir='./tests/test_app', job_config_file='job.json')

    # Update job config to include email and allocation
    job_config = JM.stage_job(job_config['job_id'],
            email="test@test.com", allocation=ALLOCATION)
    assert job_config['email']=="test@test.com"
    assert job_config['allocation']==ALLOCATION

    # Get job config now, should be updated
    new_job_config = JM.load_job(job_config['job_id'])
    assert new_job_config['email']=="test@test.com"
    assert new_job_config['allocation']==ALLOCATION

    # Fail to save job config -> Example bad job_dir path
    with pytest.raises(Exception) as e:
        bad_config = job_config
        bad_config['job_dir'] = '/bad/path'
        JM._save_job_config(bad_config)

    # Fail to load job config -> Example: bad job id
    with pytest.raises(Exception) as e:
        bad_job = JM.load_job('bad_job')

    # Get input job file from job with input file
    input_file_path = JM.get_job_file(job_config['job_id'], 'test_input_file',
            dest_dir='./tests')
    with open(input_file_path, 'r') as f:
        assert f.read()=="hello\nworld\n"

    # Get job file that doesn't exist
    with pytest.raises(Exception) as e:
        bad_file = JM.get_job_file(job_config['job_id'], 'bad_file')

    # Fail to get job file (some download error maybe)
    with patch.object(TACCJobManager, 'get_file',
            side_effect=Exception('Mock get_file error')):
        with pytest.raises(Exception) as e:
            bad_file = JM.get_job_file(job_config['job_id'], 'test_input_file', dest_dir='./tests')

    # Cleanup files just downloaded
    os.remove(input_file_path)
    os.rmdir(os.path.join('.', 'tests', job_config['job_id']))

    # Send job file
    sent_file_path = JM.send_job_file(job_config['job_id'],
            './tests/test_send_file', dest_dir='.')
    job_files = JM.ls_job(job_config['job_id'])
    assert 'test_send_file' in job_files

    # Fail to send job file
    with pytest.raises(Exception) as e:
        bad_send = JM.send_job_file(job_config['job_id'], './tests/bad_file', dest_dir='.')

    # Peak at job we just sent
    input_file_text = JM.peak_job_file(job_config['job_id'], 'test_send_file')
    assert input_file_text=="hello\nagain\n"

    # Fail to submit job because SLURM error
    with patch.object(TACCJobManager, '_execute_command',
            return_value="FAILED\n"):
        with pytest.raises(Exception) as e:
            bad_submit = JM.submit_job(job_config['job_id'])

    # Cancel job before its submitted
    with pytest.raises(Exception) as e:
        bad_cancel = JM.cancel_job(job_config['job_id'])

    # Succesfully submit job
    submitted_job = JM.submit_job(job_config['job_id'])
    assert submitted_job['slurm_id'] is not None

    # Fail to try to submit job again
    with pytest.raises(Exception) as e:
        _ = JM.submit_job(job_config['job_id'])

    # Forced failure to cancel job -> slurm error
    with patch.object(TACCJobManager, '_execute_command',
            side_effect=Exception('Mock slurm error')):
        with pytest.raises(Exception) as e:
            _ = JM.cancel_job(job_config['job_id'])

    # Successfully cancel job we just submitted
    canceled = JM.cancel_job(job_config['job_id'])

    # Fail to re-cancel job
    with pytest.raises(Exception) as e:
        bad_cancel = JM.cancel_job(job_config['job_id'])

    # Fail to submit job because of slurm error
    with patch.object(TACCJobManager, '_execute_command',
            side_effect=Exception('Execute command error')):
        with pytest.raises(Exception) as e:
            bad_deploy = JM.cancel_job(job_config['job_id'])

    # Cleanup non existent job
    bad_cleanup = JM.cleanup_job('bad_job')

    # Cleanup jobs we set-up
    _ = JM.cleanup_job(job_config['job_id'])



# def test_main(capsys):
#     """CLI Tests"""
#     # capsys is a pytest fixture that allows asserts agains stdout/stderr
#     # https://docs.pytest.org/en/stable/capture.html
#     main(["7"])
#     captured = capsys.readouterr()
#     assert "The 7-th Fibonacci number is 13" in captured.out
