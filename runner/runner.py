import sys, os, signal
import qcow2
from time import gmtime, strftime
import subprocess
# -----For local test environment only
import resource
resource.setrlimit(resource.RLIMIT_CORE, (-1, -1))
# -----
#TODO: Replace 'except as' with a general format for py 2.4-2.7
#TODO: Replace 'with' by a safe destructor


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

    The class sets up test environment, generate a test image and executes
    qemu_img with specified arguments and generated image provided. All logs
    are collected.
    """

    def __init__(self, work_dir, exec_bin=None):
        """Set test environment in a specified work directory.

        Path to qemu_img will be retrieved from 'QEMU_IMG' environment
        variable, if it's not specified.
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
        except OSError as e:
            print >>sys.stderr, 'Error: The working directory cannot be used.'\
                'Reason: ', os.strerror(e[1])
            raise

        self.log = open(os.path.join(self.current_dir, "test.log"), "w")


    def _qemu_img(self, *args):
        """ Start qemu_img with specified arguments and return an exit code or
        kill signal depending on result of an execution.

        'qemu_img' logs are collected to a file.
        """

        devnull = open('/dev/null', 'r+')
        return subprocess.call(self.exec_bin + list(args) +
                               ['test_image.qcow2'], stdin=devnull,
                               stdout=self.log, stderr=self.log)


    def execute(self, *args):
        """ Execute a test.

        The method creates a test image, runs 'qemu_img' and analyzes its exit
        code.
        """
        os.chdir(self.current_dir)
        seed = qcow2.create_image('test_image.qcow2', 4*512)
        multilog("Seed: {0}\nTest directory: {1}\n".format(seed, \
                    self.current_dir), sys.stdout, self.log)
        try:
            retcode = self._qemu_img(*args)
        except OSError as e:
            multilog("Error: Test terminated. Reason: {0}\n"\
                     .format(e[1]), sys.stderr, self.log)
            raise Exception('Internal error')

        if retcode < 0:
            multilog('FAIL: Test terminated by signal {0}\n'
                        .format(str_signal(-retcode)), sys.stderr, self.log)
        else:
            multilog("PASS: Application exited with the status '{0}'\n"
                        .format(os.strerror(retcode)), sys.stdout, self.log)


    def __enter__(self):
        """ Return an instance for 'with' statement
        """

        return self


    def __exit__(self, *args):
        """ Restore environment after a test execution
        """
        self.log.close()
        os.chdir(self.init_path)

if __name__ == '__main__':

    if not len(sys.argv) == 2:
        print('Usage: runner.py "/path/to/work/dir"')
        sys.exit(1)
    else:
        try:
            with testEnv(sys.argv[1]) as test:
                test.execute('check')
        #Silent exit on user break
        except (KeyboardInterrupt, SystemExit):
            sys.exit(1)
        except Exception as e:
            print("FAIL: %s"  %e)
            sys.exit(1)
