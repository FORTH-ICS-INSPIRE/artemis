import traceback
import errno
import os
import os.path
import signal
import time
from pid import PidFile
from multiprocessing import Process
import setproctitle


class _PIDFile(object):
    """
    A lock file that stores the PID of the owning process.

    The PID is stored when the lock is acquired, not when it is created.
    """

    def __init__(self, path):
        self._path = path
        self._lock = None

    def _make_lock(self):
        directory, filename = os.path.split(self._path)
        return PidFile(filename, directory, register_term_signal_handler=False)

    def acquire(self):
        self._make_lock().create()

    def release(self):
        self._make_lock().close()
        try:
            os.remove(self._path)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise

    def read_pid(self):
        """
        Return the PID of the process owning the lock.

        Returns ``None`` if no lock is present.
        """
        try:
            with open(self._path, 'r') as f:
                s = f.read().strip()
                if not s:
                    return None
                return int(s)
        except IOError as e:
            if e.errno == errno.ENOENT:
                return None
            raise


def _block(predicate, timeout):
    """
    Block until a predicate becomes true.

    ``predicate`` is a function taking no arguments. The call to
    ``_block`` blocks until ``predicate`` returns a true value. This
    is done by polling ``predicate``.

    ``timeout`` is either ``True`` (block indefinitely) or a timeout
    in seconds.

    The return value is the value of the predicate after the
    timeout.
    """
    if timeout:
        if timeout is True:
            timeout = float('Inf')
        timeout = time.time() + timeout
        while not predicate() and time.time() < timeout:
            time.sleep(0.1)
    return predicate()


class Service(Process):
    """
    A background service.

    This class provides the basic framework for running and controlling
    a background daemon. This includes methods for starting the daemon
    (including things like proper setup of a detached deamon process),
    checking whether the daemon is running, asking the daemon to
    terminate and for killing the daemon should that become necessary.

    .. py:attribute:: logger

        A :py:class:`logging.Logger` instance.

    .. py:attribute:: files_preserve

        A list of file handles that should be preserved by the daemon
        process. File handles of built-in Python logging handlers
        attached to :py:attr:`logger` are automatically preserved.
    """

    def __init__(self, pid_dir='/dev/shm'):
        """
        Constructor.

        ``name`` is a string that identifies the daemon. The name is
        used for the name of the daemon process, the PID file and for
        the messages to syslog.

        ``pid_dir`` is the directory in which the PID file is stored.
        """
        super().__init__()
        self.pid_file = _PIDFile(os.path.join(pid_dir, self.name + '.pid'))
        self.worker = None

    def is_running(self):
        """
        Check if the daemon is running.
        """
        pid = self.get_pid()
        if pid is None:
            return False
        # The PID file may still exist even if the daemon isn't running,
        # for example if it has crashed.
        try:
            os.kill(pid, 0)
        except OSError as e:
            if e.errno == errno.ESRCH:
                # In this case the PID file shouldn't have existed in
                # the first place, so we remove it
                self.pid_file.release()
                return False
            # We may also get an exception if we're not allowed to use
            # kill on the process, but that means that the process does
            # exist, which is all we care about here.
        return True

    def get_pid(self):
        """
        Get PID of daemon process or ``None`` if daemon is not running.
        """
        return self.pid_file.read_pid()

    def stop(self, block=False):
        """
        Tell the daemon process to stop.

        Sends the SIGTERM signal to the daemon process, requesting it
        to terminate.

        If ``block`` is true then the call blocks until the daemon
        process has exited. This may take some time since the daemon
        process will complete its on-going backup activities before
        shutting down. ``block`` can either be ``True`` (in which case
        it blocks indefinitely) or a timeout in seconds.

        The return value is ``True`` if the daemon process has been
        stopped and ``False`` otherwise.

        .. versionadded:: 0.3
            The ``block`` parameter
        """
        pid = self.get_pid()
        if not pid:
            raise ValueError('Daemon is not running.')
        os.kill(pid, signal.SIGTERM)
        return _block(lambda: not self.is_running(), block)

    def kill(self, block=False):
        """
        Kill the daemon process.

        Sends the SIGKILL signal to the daemon process, killing it. You
        probably want to try :py:meth:`stop` first.

        If ``block`` is true then the call blocks until the daemon
        process has exited. ``block`` can either be ``True`` (in which
        case it blocks indefinitely) or a timeout in seconds.

        Returns ``True`` if the daemon process has (already) exited and
        ``False`` otherwise.

        The PID file is always removed, whether the process has already
        exited or not. Note that this means that subsequent calls to
        :py:meth:`is_running` and :py:meth:`get_pid` will behave as if
        the process has exited. If you need to be sure that the process
        has already exited, set ``block`` to ``True``.

        .. versionadded:: 0.5.1
            The ``block`` parameter
        """
        pid = self.get_pid()
        if not pid:
            raise ValueError('Daemon is not running.')
        try:
            os.kill(pid, signal.SIGKILL)
            return _block(lambda: not self.is_running(), block)
        except OSError as e:
            if e.errno == errno.ESRCH:
                raise ValueError('Daemon is not running.')
            raise
        finally:
            self.pid_file.release()

    def run(self):
        pid = self.get_pid()
        if pid:
            if self.is_running():
                raise ValueError('Daemon is already running at PID %d.' % pid)

        # The default is to place the PID file into ``/var/run``. This
        # requires root privileges. Since not having these is a common
        # problem we check a priori whether we can create the lock file.
        try:
            self.pid_file.acquire()
        finally:
            self.pid_file.release()

        def runner():
            try:
                # We acquire the PID as late as possible, since its
                # existence is used to verify whether the service
                # is running.
                self.pid_file.acquire()
                self.run_worker()
                self.pid_file.release()
            except Exception:
                traceback.print_exc()

        try:
            setproctitle.setproctitle(self.name)
            signal.signal(signal.SIGTERM, self.exit)
            signal.signal(signal.SIGINT, self.exit)
            runner()
        except Exception as e:
            traceback.print_exc()

    def exit(self, signum, frame):
        if self.worker is not None:
            self.worker.should_stop = True
