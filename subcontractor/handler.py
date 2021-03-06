import logging
import time
import threading
from importlib import import_module

class JobWorker( threading.Thread ):
  def __init__( self, contractor, cookie, job_id, function, paramaters, semaphore ):
    super().__init__()
    self.contractor = contractor
    self.cookie = cookie
    self.job_id = job_id
    self.function = function
    self.paramaters = paramaters
    self.semaphore = semaphore

  def run( self ):
    try:
      logging.debug( 'handler: acquring lock for "{0}"...'.format( self.job_id ) )
      self.semaphore.acquire()
      logging.debug( 'handler: lock acquired for "{0}"...'.format( self.job_id ) )

      try:
        data = self.function( self.paramaters )
      except Exception as e:
        logging.exception( 'handler: Exception with function "{0}" paramaters "{1}"'.format( self.function, self.paramaters ) )
        self.contractor.jobError( self.job_id, 'Unhandled Exception "{0}"({1})'.format( e, type( e ).__name__ ), self.cookie )
        return

    finally:
      self.semaphore.release()
      logging.debug( 'handler: log for "{0}" released'.format( self.job_id ) )

    if not isinstance( data, dict ):
      logging.error( 'handler: result from function was not a dict, got "{0}"({1})'.format( str( data )[ 0:50 ], type( data ).__name__ ) )
      self.contractor.jobError( self.job_id, 'result was not a dict, got "{0}"({1})'.format( data, type( data ).__name__ ), self.cookie )

    response = self.contractor.jobResults( self.job_id, data, self.cookie ) # this is after releasing the semaphore so we are not holding things up if it requires retries
    logging.info( 'handler: job "{0}" complete, contractor said "{1}"'.format( self.job_id, response ) )

class Handler():
  def __init__( self, contractor ):
    super().__init__()
    self.contractor = contractor
    self.max_concurent_jobs = 0 # there is not a semaphore to inforce this, this is used to limit the number of jobs being requested
    self.job_delay = 5
    self.job_queue = []
    self.module_map = {}
    self.semaphore_map = {}

  @property
  def empty_slots( self ):
    return self.max_concurent_jobs - len( self.job_queue )

  @property
  def module_list( self ):
    return list( self.module_map.keys() )

  def registerModule( self, path, limit ):
    module = import_module( path )

    logging.info( 'handler: registering module "{0}" with limit "{1}"...'.format( module.MODULE_NAME, limit ) )
    self.module_map[ module.MODULE_NAME ] = module.MODULE_FUNCTIONS
    self.semaphore_map[ module.MODULE_NAME ] = threading.BoundedSemaphore( limit )

  def setLimits( self, job_delay=None, max_concurent_jobs=None ):
    if max_concurent_jobs is not None and ( max_concurent_jobs < 0 or max_concurent_jobs > 100 ):
      raise TypeError( 'max_concurent_jobs is invalid' )

    if job_delay is not None and ( job_delay < 0 or job_delay > 60 ):
      raise TypeError( 'job_delay is invalid' )

    if job_delay is not None:
      logging.info( 'handler: setting job_delay to "{0}"'.format( job_delay ) )
      self.job_delay = job_delay

    if max_concurent_jobs is not None:
      logging.info( 'handler: setting max_concurent_jobs to "{0}"'.format( max_concurent_jobs ) )
      self.max_concurent_jobs = max_concurent_jobs

  def addJobs( self, job_list ):
    logging.info( 'handler: adding more jobs "{0}"....'.format( job_list ) )

    for job in job_list:
      try:
        semaphore = self.semaphore_map[ job[ 'module' ] ]
      except KeyError:
        logging.error( 'handler: Unable to find semaphore for module "{0}"'.format( job[ 'module' ] ) )
        continue

      try:
        function = self.module_map[ job[ 'module' ] ][ job[ 'function' ] ]
      except KeyError:
        logging.error( 'handler: Unable to find function "{0}" in module "{1}", job dropped.'.format( job[ 'function' ], job[ 'module' ] ) )
        continue

      worker = JobWorker( self.contractor, job[ 'cookie' ], job[ 'job_id' ], function, job[ 'paramaters' ], semaphore )
      worker.start()

  def wait( self ):
    while len( threading.enumerate() ) > 1:
      logging.info( 'handler: Waiting for {0} workers to finish'.format( len( threading.enumerate() ) - 1 ) )
      time.sleep( 2 )

  def logStatus( self ):
    for module_name in self.module_map:
      logging.info( 'handler: module "{0}": {1} slots aviable'.format( module_name, self.semaphore_map[ module_name ]._value ) )
