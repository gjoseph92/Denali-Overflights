from multiprocessing.managers import SyncManager
import time
import sys
import functools

######################################################################################
## Hacky workarounds for Windows pickling issues:
## http://stackoverflow.com/questions/25631266/cant-pickle-class-main-jobqueuemanager
import Queue
from functools import partial

class _PickleQueue(Queue.Queue):
    """ A picklable queue. """   
    def __getstate__(self):
        # Only pickle the state we care about
        return (self.maxsize, self.queue, self.unfinished_tasks)

    def __setstate__(self, state):
        # Re-initialize the object, then overwrite the default state with
        # our pickled state.
        _PickleQueue.__init__(self)
        self.maxsize = state[0]
        self.queue = state[1]
        self.unfinished_tasks = state[2]

class _JobQueueManager(SyncManager):
    pass

def _identity(x): return x

class remote:
    """
    Decorator to make a function runnable remotely.
    
    Calling the function will return a Task (just a dict),
    which can be passed to the conductor to be run by your workers.
    
    The actual function is stored in the attribute `function`
    (used by workers who import your script).
    """
    def __init__(self, fun):
        self.function = fun
        functools.update_wrapper(self, fun)
    def __call__(self, *args, **kwargs):
        return {
            "name": self.__name__,
            "args": args,
            "kwargs": kwargs
        }

class Conductor:
    port = 5050
    authkey = 'distribute'

    def __init__(self):

        ## Get local ip (but not 127.0.0.1)
        import socket
        ip = socket.gethostbyname(socket.gethostname())

        jobQ = _PickleQueue()
        resQ = _PickleQueue()

        _JobQueueManager.register('get_job_q', callable= partial(_identity, jobQ) )
        _JobQueueManager.register('get_res_q', callable= partial(_identity, resQ) )

        manager = _JobQueueManager(address=(ip, self.port), authkey= self.authkey)
        address, port = manager.get_server().address
        manager.start()
        print "Started the conductor at {} on port {}".format(address, port)
        
        self._manager = manager
        self._jobQ = manager.get_job_q()
        self._resQ = manager.get_res_q()
        
    def makeTask(self, name, *args):
        """
        It's preferred to use the `@distribute.remote` decorator,
        but if you're using a separate file for your remote methods
        (or you can't access the remote methods file), you can manually
        make a task for any remote function by name.
        """
        return {
            "name": name,
            "args": args
        }

    def __call__(self, tasks):
        """
        Call a Conductor instance with a single task or iterable of tasks to run them
        all remotely.
        """
        if isinstance(tasks, dict):
            tasks = (tasks,)
        self.runTasks(tasks)

    def runTasks(self, tasks):
        """
        Takes an iterable of tasks and enqueues them to run remotely.
        Returns a list of their results (*not necessary in the same order*)
        only once all are complete. (It's very much blocking, that's the point.)

        Displays a progress bar while tasks are running.
        """
        tasknames = set()
        numtasks = 0
        for task in tasks:
            tasknames.add(task['name'])
            numtasks = numtasks + 1
            self._jobQ.put(task)

        if numtasks == 0:
            return

        print "*** Starting task{} {}...\n".format('s' if len(tasknames) > 1 else '',
                                                   ', '.join(tasknames))

        results = []
        try:
            while len(results) < numtasks:
                try:
                    result = self._resQ.get(True, 5)
                    if type(result) is tuple and issubclass(result[0], Exception):
                        print "*** Error in remote method:"
                        print "*" * 50
                        print result[2]
                        print "*" * 50
                        print
                        # raise result[0], result[1]

                    results.append(result)
                    # print "    {} / {} complete".format(len(results), numtasks)
                    self._progressBar(len(results), numtasks)
                except Queue.Empty:
                    continue
        except (KeyboardInterrupt, SystemExit):
            print "*** Received KeyboardInterrupt, shutting down..."
            self.close()
            raise

        print ""

        if not self._jobQ.empty():
            print "*** Job queue is not empty, that's weird. Things will go wrong now."

        return results

    def close(self):
        print "Clearing queue..."
        while True:
            try:
                self._jobQ.get_nowait()
            except Queue.Empty:
                break
        print "Shutting down manager..."
        self._manager.shutdown()

    _lastBlocks = 41
    def _progressBar(self, nComplete, nJobs):
        progress = nComplete / float(nJobs)
        barLength = 35
        blocksComplete = int(round(barLength*progress))

        now = time.time()

        if self._lastBlocks > blocksComplete:
            self._lastBlocks = 0.0
            self._startTime = now
            self._lastProgress = now

        if blocksComplete > self._lastBlocks or now - self._lastProgress > 1:

            elapsed = now - self._startTime
            remaining = (elapsed / progress) - elapsed

            blocks = "#"*blocksComplete
            dashes = "-"*(barLength-blocksComplete)
            text = "\r{} [{}{}] {:.0%} {}/{} - {} left".format( time.strftime("%H:%M:%S", time.gmtime(elapsed)),
                                                             blocks, dashes, progress,
                                                             nComplete, nJobs,
                                                             time.strftime("%H:%M:%S", time.gmtime(remaining)) )
            sys.stdout.write(text)
            sys.stdout.flush()

            self._lastBlocks = blocksComplete
            self._lastProgress = now

################################
## Command line: use as a worker

def work(methodsFile, ip):
    """
    Run forever as a worker, listening for tasks implemented in `methodsFile` from
    a conductor at `ip`.

    The methods file *could* be the same file that's running the conductor---in that case,
    any functions decorated with `@distribute.remote` will probably be the ones run.

    However, `distribute.py` isn't discerning about what remote methods it'll run---if it's
    callable, we'll run it. So even functions that aren't decorated with `@distribute.remote`
    are fair game. Likewise, the methods file doesn't need to `import distribute` or anything,
    you can give any old Python file and whatever functions it has are fair game.
    """
    import socket
    import traceback
    import os
    import importlib

    # ip = 'localhost'
    print "Starting a worker for {}...".format(methodsFile)

    ###############
    ## Load methods

    path, filename = os.path.split(methodsFile)
    if path != '':
        print "*** Only imports from the same directory are possible right now"
        resQ.put( (ImportError, None, "Could not import {}: only imports from same directory are currently supported".format(methodsFile)) )
        sys.exit(1)

    moduleName = filename.replace('.py', '') if filename.endswith('.py') else filename

    tasks = importlib.import_module(moduleName)

    ## Run forever, processing jobs as they come, and reconnecting as necessary
    while True:
        _JobQueueManager.register('get_job_q')
        _JobQueueManager.register('get_res_q')
        manager = _JobQueueManager(address= (ip, Conductor.port), authkey= Conductor.authkey)
        print "Waiting for tasks from {} on port {}...".format(ip, Conductor.port)

        ##########
        ## Connect

        while True:
            # The connection socket times out after ~20sec, keep trying it forever
            try:
                manager.connect()
                break
            except (KeyboardInterrupt):
                print "Giving up on connection, goodbye..."
                sys.exit(1)
                raise
            except socket.error:
                continue

        jobQ = manager.get_job_q()
        resQ = manager.get_res_q()

        ######################################
        ## Reload methods in case file changed

        tasks = reload(tasks)

        ###########################
        ## Run jobs from jobs queue

        connected = True
        while connected:
            try:
                task = jobQ.get(True, 5)
                method = getattr(tasks, task['name'])
                if hasattr(method, 'function'):
                    # if it's a function we decorated with @distribute.remote, pull out the function itself
                    method = method.function
                print "*** Running {}({})...".format(task['name'], ', '.join( map(str, task['args']) ))
                result = method(*task['args'], **task['kwargs'])
                jobQ.task_done()
                resQ.put(result)
                print "    completed."

            except (KeyboardInterrupt, SystemExit):
                print "*** Received KeyboardInterrupt, shutting down..."
                jobQ.put(task)  # return the task so someone else can do it (assumes tasks are idempotent!)
                sys.exit(1)
            except AttributeError as e:
                if task['name'] in e.message:
                    print "*** Tried to run task '{}', which doesn't exist".format(task['name'])
                    try:
                        jobQ.task_done()
                        resQ.put( (NameError, '', "NameError: name '{}' not defined in {}".format(task['name'], methodsFile)) )
                    except IOError:
                        ## Conductor probably shut itself down because of the error we previously sent it
                        pass
                else:
                    # AttributeError came from inside the remote method, pass it along
                    exc_info = sys.exc_info()
                    print "    Error executing method: {}".format(exc_info)
                    try:
                        jobQ.task_done()
                        resQ.put( (exc_info[0], exc_info[1], traceback.format_exc() ) )
                    except IOError:
                        ## Conductor probably shut itself down because of the error we previously sent it
                        pass
            except Queue.Empty:
                continue
            except IOError:
                print "Disconnected from conductor."
                connected = False
            except:
                exc_info = sys.exc_info()
                print "    Error executing method: {}".format(exc_info[0])
                try:
                    jobQ.task_done()
                    resQ.put( (exc_info[0], exc_info[1], traceback.format_exc() ) )
                except IOError:
                    ## Conductor probably shut itself down because of the error we previously sent it
                    pass
    

if __name__ == '__main__':
    import sys

    args = sys.argv
    if len(args) != 3:
        if len(args) == 1:
            # Get args interactively, helpful for Windows
            print "Enter name of methods file"
            methods_file = raw_input(">>> ")
            print "Enter IP address of conductor"
            ip = raw_input(">>> ")
            args.extend([methods_file, ip])
        else:
            print "Useage: {} <methods_file.py> <conductor_ip>".format(args[0])
            sys.exit(1)

    work(*args[1:])