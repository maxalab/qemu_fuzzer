import sys, os, signal
import qcow2
from time import gmtime, strftime
import subprocess
from shutil import rmtree
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


class testEnv(object):
    """ Trivial test object

    The class sets up test environment, generates a test image and executes
    qemu_img with specified arguments and a test image provided. All logs
    are collected.
    Summary log will contain short descriptions and statuses of all tests in
    a run.
    Test log will include application ('qemu-img') logs besides info sent
    to the summary log.
    """
    def __init__(self, work_dir, run_log, exec_bin=None):
        """Set test environment in a specified work directory.

        Path to qemu_img will be retrieved from 'QEMU_IMG' environment
        variable, if not specified.
        """

        self.init_path = os.getcwd()
        self.work_dir = work_dir
        self.current_dir = os.path.join(work_dir, strftime("%Y_%m_%d_%H-%M-%S",
                                                           gmtime()))
        if exec_bin is not None:
            self.exec_bin = exec_bin
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

    def _qemu_img(self, *args):
        """ Start qemu_img with specified arguments and return an exit code or
        a kill signal depending on result of an execution.
        """

        devnull = open('/dev/null', 'r+')
        return subprocess.call(self.exec_bin + list(args) +
                               ['test_image.qcow2'], stdin=devnull,
                               stdout=self.log, stderr=self.log)


    def execute(self, *args):
        """ Execute a test.

        The method creates a test image, runs 'qemu_img' and analyzes its exit
        status. If the application was killed by a signal, the test is marked
        as failed.
        """
        os.chdir(self.current_dir)
        seed = qcow2.create_image('test_image.qcow2', 4*512)
        multilog("Seed: %s\nTest directory: %s\n" %(seed, self.current_dir),\
                 sys.stdout, self.log, self.parent_log)
        try:
            retcode = self._qemu_img(*args)
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
        self.parent_log.close()
        os.chdir(self.init_path)
        if self.result:
            rmtree(self.current_dir)


if __name__ == '__main__':

    if not len(sys.argv) == 2:
        print('Usage: runner.py "/path/to/work/dir"')
        sys.exit(1)
    else:
        work_dir = sys.argv[1]
        # run_log created in 'main', because multiple tests are expected to \
        # log in it
        run_log = os.path.join(work_dir, 'run_' + \
                               strftime("%Y_%m_%d_%H-%M", gmtime()) + '.log')
        try:
            test = testEnv(work_dir, run_log)
        except Exception:
            e = sys.exc_info()[1]
            print("FAIL: %s"  %e)
            sys.exit(1)

        # Python 2.4 doesn't support 'finally' and 'except' in the same 'try'
        # block
        try:
            try:
                test.execute('check')
                #Silent exit on user break
            except (KeyboardInterrupt, SystemExit):
                sys.exit(1)
            except Exception:
                e = sys.exc_info()[1]
                print("FAIL: %s"  %e)
                sys.exit(1)
        finally:
            test.finish()
