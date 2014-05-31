# Tool for running fuzz tests
#
# Copyright (C) 2014 Maria Kustova <maria.k@catit.be>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import sys, os, signal
import qcow2
from time import gmtime, strftime
import subprocess
from shutil import rmtree
import getopt
# -----For local test environment only
import resource
resource.setrlimit(resource.RLIMIT_CORE, (-1, -1))
# -----

def multilog(msg, *output):
    """ Write an object to all of specified file descriptors
    """

    for fd in output:
        fd.write(msg)
        fd.flush()


def str_signal(sig):
    """ Convert a numeric value of a system signal to the string one
    defined by the current operational system
    """

    for k, v in signal.__dict__.items():
        if v == sig:
            return k


class TestEnv(object):
    """ Trivial test object

    The class sets up test environment, generates a test image and executes
    qemu_img with specified arguments and a test image provided. All logs
    are collected.
    Summary log will contain short descriptions and statuses of all tests in
    a run.
    Test log will include application ('qemu-img') logs besides info sent
    to the summary log.
    """

    def __init__(self, work_dir, run_log, exec_bin=None, cleanup=True):
        """Set test environment in a specified work directory.

        Path to qemu_img will be retrieved from 'QEMU_IMG' environment
        variable, if not specified.
        """

        self.init_path = os.getcwd()
        self.work_dir = work_dir
        self.current_dir = os.path.join(work_dir, strftime("%Y_%m_%d_%H-%M-%S",
                                                           gmtime()))
        if exec_bin is not None:
            self.exec_bin = exec_bin.strip().split(' ')
        else:
            self.exec_bin = os.environ.get('QEMU_IMG', 'qemu-img').strip()\
            .split(' ')

        try:
            os.makedirs(self.current_dir)
        except OSError:
            e = sys.exc_info()[1]
            print >>sys.stderr, 'Error: The working directory cannot be used.'\
                ' Reason: %s' %e[1]
            raise Exception('Internal error')

        self.log = open(os.path.join(self.current_dir, "test.log"), "w")
        self.parent_log = open(run_log, "a")
        self.result = False
        self.cleanup = cleanup

    def _qemu_img(self, q_args):
        """ Start qemu_img with specified arguments and return an exit code or
        a kill signal depending on result of an execution.
        """
        devnull = open('/dev/null', 'r+')
        return subprocess.call(self.exec_bin \
                               + q_args +
                               ['test_image.qcow2'], stdin=devnull,
                               stdout=self.log, stderr=self.log)


    def execute(self, q_args, seed, size=8*512):
        """ Execute a test.

        The method creates a test image, runs 'qemu_img' and analyzes its exit
        status. If the application was killed by a signal, the test is marked
        as failed.
        """
        os.chdir(self.current_dir)
        seed = qcow2.create_image('test_image.qcow2', seed, size)
        multilog("Seed: %s\nCommand: %s\nTest directory: %s\n"\
                 %(seed, " ".join(q_args), self.current_dir),\
                 sys.stdout, self.log, self.parent_log)
        try:
            retcode = self._qemu_img(q_args)
        except OSError:
            e = sys.exc_info()[1]
            multilog("Error: Start of 'qemu_img' failed. Reason: %s\n"\
                     %e[1], sys.stderr, self.log, self.parent_log)
            raise Exception('Internal error')

        if retcode < 0:
            multilog('FAIL: Test terminated by signal %s\n'
                     %str_signal(-retcode), sys.stderr, self.log, \
                     self.parent_log)
        else:
            multilog("PASS: Application exited with the code '%d'\n"
                     %retcode, sys.stdout, self.log, self.parent_log)
            self.result = True

    def finish(self):
        """ Restore environment after a test execution. Remove folders of
        passed tests
        """
        self.log.close()
        # Delimiter between tests
        self.parent_log.write("\n")
        self.parent_log.close()
        os.chdir(self.init_path)
        if self.result and self.cleanup:
            rmtree(self.current_dir)

if __name__ == '__main__':

    def usage():
        print("""
        Usage: runner.py [OPTION...] DIRECTORY

        Set up test environment in DIRECTORY and run a test in it.

        Optional arguments:
          -h, --help           display this help and exit
          -c, --command=STRING execute qemu-img with arguments specified,
                               by default STRING="check"
          -b, --binary=PATH    path to the application under test, by default
                               "qemu-img" in PATH or QEMU_IMG environment
                               variables
          -s, --seed=STRING    seed for a test image generation, by default
                               will be generated randomly
          -k, --keep_passed    don't remove folders of passed tests
        """)

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'c:hb:s:k',
                                   ['command=', 'help', 'binary=', 'seed=',
                                    'keep_passed'])
    except getopt.error:
        e = sys.exc_info()[1]
        print('Error: %s\n\nTry runner.py --help.' %e)
        sys.exit(1)

    if len(sys.argv) == 1:
        usage()
        sys.exit(1)

    command = ['check']
    cleanup = True
    test_bin = None
    seed = None
    for opt, arg in opts:
        if opt in ('-h', '--help'):
            usage()
            sys.exit()
        elif opt in ('-c', '--command'):
            command = arg.split(" ")
        elif opt in ('-k', '--keep_passed'):
            cleanup = False
        elif opt in ('-b', '--binary'):
            test_bin = arg
        elif opt in ('-s', '--seed'):
            seed = arg

    if not len(args) == 1:
        print 'Error: required parameter "DIRECTORY" missed'
        usage()
        sys.exit(1)

    work_dir = args[0]
    # run_log created in 'main', because multiple tests are expected to \
    # log in it
    # TODO: Make unique run_log names on every run (for one test per run
    # this functionality is omitted in favor of usability)
    run_log = os.path.join(work_dir, 'run.log')

    try:
        test = TestEnv(work_dir, run_log, test_bin, cleanup)
    except:
        e = sys.exc_info()[1]
        print("FAIL: %s"  %e)
        sys.exit(1)

    # Python 2.4 doesn't support 'finally' and 'except' in the same 'try'
    # block
    try:
        try:
            test.execute(command, seed)
            #Silent exit on user break
        except (KeyboardInterrupt, SystemExit):
            sys.exit(1)
        except:
            e = sys.exc_info()[1]
            print("FAIL: %s"  %e)
            sys.exit(1)
    finally:
        test.finish()
