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
from time import time
import subprocess
import random
from itertools import count
from shutil import rmtree
import getopt
import resource
resource.setrlimit(resource.RLIMIT_CORE, (-1, -1))


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


class TestException(Exception):
    """Exception for errors risen by TestEnv objects"""
    pass


class TestEnv(object):
    """ Trivial test object

    The class sets up test environment, generates a test image and executes
    application under tests with specified arguments and a test image provided.
    All logs are collected.
    Summary log will contain short descriptions and statuses of tests in
    a run.
    Test log will include application (e.g. 'qemu-img') logs besides info sent
    to the summary log.
    """

    def __init__(self, test_id, seed, work_dir, run_log, exec_bin=None,
                 cleanup=True, log_all=False):
        """Set test environment in a specified work directory.

        Path to qemu_img will be retrieved from 'QEMU_IMG' environment
        variable, if a test binary is not specified.
        """

        if seed is not None:
            self.seed = seed
        else:
            self.seed = hash(time())

        self.init_path = os.getcwd()
        self.work_dir = work_dir
        self.current_dir = os.path.join(work_dir, 'test-' + test_id)
        if exec_bin is not None:
            self.exec_bin = exec_bin.strip().split(' ')
        else:
            self.exec_bin = \
                os.environ.get('QEMU_IMG', 'qemu-img').strip().split(' ')

        try:
            os.makedirs(self.current_dir)
        except OSError:
            e = sys.exc_info()[1]
            print >>sys.stderr, \
                "Error: The working directory '%s' cannot be used. Reason: %s"\
                % (self.work_dir, e[1])
            raise TestException
        self.log = open(os.path.join(self.current_dir, "test.log"), "w")
        self.parent_log = open(run_log, "a")
        self.result = False
        self.cleanup = cleanup
        self.log_all = log_all

    def _test_app(self, q_args):
        """ Start application under test with specified arguments and return
        an exit code or a kill signal depending on result of an execution.
        """
        devnull = open('/dev/null', 'r+')
        return subprocess.call(self.exec_bin + q_args + ['test_image'],
                               stdin=devnull, stdout=self.log, stderr=self.log)

    def execute(self, q_args):
        """ Execute a test.

        The method creates a test image, runs test app and analyzes its exit
        status. If the application was killed by a signal, the test is marked
        as failed.
        """
        os.chdir(self.current_dir)
        # Seed initialization should be as close to image generation call
        # as posssible to avoid a corruption of random sequence
        random.seed(self.seed)
        image_generator.create_image('test_image')
        test_summary = "Seed: %s\nCommand: %s\nTest directory: %s\n" \
                       % (self.seed, " ".join(q_args), self.current_dir)
        try:
            retcode = self._test_app(q_args)
        except OSError:
            e = sys.exc_info()[1]
            multilog(test_summary + "Error: Start of '%s' failed. " \
                     "Reason: %s\n\n" % (os.path.basename(self.exec_bin[0]),
                                         e[1]),
                     sys.stderr, self.log, self.parent_log)
            raise TestException

        if retcode < 0:
            multilog(test_summary + "FAIL: Test terminated by signal %s\n\n"
                     % str_signal(-retcode), sys.stderr, self.log,
                     self.parent_log)
        elif self.log_all:
            multilog(test_summary + "PASS: Application exited with the code" +
                     " '%d'\n\n" % retcode, sys.stdout, self.log,
                     self.parent_log)
            self.result = True
        else:
            self.result = True

    def finish(self):
        """ Restore environment after a test execution. Remove folders of
        passed tests
        """
        self.log.close()
        self.parent_log.close()
        os.chdir(self.init_path)
        if self.result and self.cleanup:
            rmtree(self.current_dir)

if __name__ == '__main__':

    def usage():
        print """
        Usage: runner.py [OPTION...] DIRECTORY PATH

        Set up test environment in DIRECTORY and run a test in it. Test image
        generator should be specified via PATH to it.

        Optional arguments:
          -h, --help                    display this help and exit
          -b, --binary=PATH             path to the application under test,
                                        by default "qemu-img" in PATH or
                                        QEMU_IMG environment variables
          -c, --command=STRING          execute the tested application
                                        with arguments specified,
                                        by default STRING="check"
          -s, --seed=STRING             seed for a test image generation,
                                        by default will be generated randomly
          -k, --keep_passed             don't remove folders of passed tests
          -v, --verbose                 log information about passed tests
        """

    def run_test(test_id, seed, work_dir, run_log, test_bin, cleanup, log_all,
                 command):
        """Setup environment for one test and execute this test"""
        try:
            test = TestEnv(test_id, seed, work_dir, run_log, test_bin, cleanup,
                           log_all)
        except TestException:
            sys.exit(1)

        # Python 2.4 doesn't support 'finally' and 'except' in the same 'try'
        # block
        try:
            try:
                test.execute(command)
            # Silent exit on user break
            except TestException:
                sys.exit(1)
        finally:
            test.finish()

    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'c:hb:s:kv',
                                       ['command=', 'help', 'binary=', 'seed=',
                                        'keep_passed', 'verbose'])
    except getopt.error:
        e = sys.exc_info()[1]
        print "Error: %s\n\nTry 'runner.py --help' for more information" % e
        sys.exit(1)

    command = ['check']
    cleanup = True
    log_all = False
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
        elif opt in ('-v', '--verbose'):
            log_all = True
        elif opt in ('-b', '--binary'):
            test_bin = os.path.realpath(arg)
        elif opt in ('-s', '--seed'):
            seed = arg

    if not len(args) == 2:
        print "Missed parameter\nTry 'runner.py --help' " \
            "for more information"
        sys.exit(1)

    work_dir = os.path.realpath(args[0])
    # run_log is created in 'main', because multiple tests are expected to \
    # log in it
    run_log = os.path.join(work_dir, 'run.log')

    # Add the module path to sys.path
    sys.path.append(os.path.dirname(os.path.realpath(args[1])))
    # Remove a script extension if any
    generator_name = os.path.splitext(os.path.basename(args[1]))[0]
    try:
        image_generator = __import__(generator_name)
    except ImportError:
        e = sys.exc_info()[1]
        print "Error: The image generator '%s' cannot be imported.\n" \
            "Reason: %s" % (generator_name, e)
        sys.exit(1)

    # If a seed is specified, only one test will be executed.
    # Otherwise runner will terminate after a keyboard interruption
    for test_id in count(1):
        try:
            run_test(str(test_id), seed, work_dir, run_log, test_bin, cleanup,
                     log_all, command)
        except (KeyboardInterrupt, SystemExit):
            sys.exit(1)

        if seed is not None:
            break
