#!/usr/bin/env python
"""
HiveAggregator
Developed by Trevor Stanhope

HiveAggregator is a minimal CherryPy instance

TODO:
- Log post --> train learners
"""

# Libraries
import json
import ast
import cherrypy
import os
import sys
import numpy
from datetime import datetime, timedelta
from cherrypy.process.plugins import Monitor
from cherrypy import tools
from pymongo import MongoClient
from bson import json_util
import zmq
from sklearn import svm

# Constants
try:
    CONFIG_FILE = sys.argv[1]
except Exception as err:
    CONFIG_FILE = 'settings.json'

# HiveAggregator CherryPy server
class HiveAggregator:

    ## Initialize
    def __init__(self, config_file):
        print('\n----------- Initializing -----------')
        self.init_config(config_file)
        self.init_zmq()
        self.init_cherrypy()
        self.init_mongo()
        self.init_sklearn()
    
    ## Load Configuration
    def init_config(self, config_file):
        print('[Loading Config File]')
        with open(config_file) as config:
            settings = json.loads(config.read())
            for key in settings:
                try:
                    getattr(self, key)
                except AttributeError as error:
                    print('\t' + key + ' : ' + str(settings[key]))
                    setattr(self, key, settings[key])
    
    ## Initialize ZMQ
    def init_zmq(self):      
        print('[Initializing ZMQ] %s' % datetime.strftime(datetime.now(), self.TIME_FORMAT))
        try:
            self.context = zmq.Context()
            self.socket = self.context.socket(zmq.REP)
            self.socket.bind(self.ZMQ_SERVER)
            print('\tOKAY')
        except Exception as error:
            print('\tERROR: %s' % str(error))
    
    ## Initialize CherryPy
    def init_cherrypy(self):   
        print('[Initializing Monitors] %s' % datetime.strftime(datetime.now(), self.TIME_FORMAT))
        try:
            Monitor(cherrypy.engine, self.listen, frequency=self.CHERRYPY_INTERVAL).subscribe()
            print('\tOKAY')
        except Exception as error:
            print('\tERROR: %s' % str(error))     
    
    ## Initialize MongoDB
    def init_mongo(self):
        print('[Initializing Mongo] %s' % datetime.strftime(datetime.now(), self.TIME_FORMAT))
        try:    
            self.mongo_client = MongoClient(self.MONGO_ADDR, self.MONGO_PORT)
            self.mongo_db = self.mongo_client[self.MONGO_DB]
            print('\tOKAY')
        except Exception as error:
            print('\tERROR: %s' % str(error))
    
    ## Initialize SKlearn
    def init_sklearn(self):     
        print('[Initializing SKlearn] %s' % datetime.strftime(datetime.now(), self.TIME_FORMAT))
        try:
            ## Learning Estimators
            self.svc_health = svm.SVC(kernel='rbf')
            self.svc_environment = svm.SVC(kernel='rbf')
            self.svc_activity = svm.SVC(kernel='rbf')
            print('\tOKAY')
        except Exception as error:
            print('\tERROR: %s' % str(error))
    
    ## Train Estimators
    def train_estimators(self, log):
        print('[Training Estimators] %s' % datetime.strftime(datetime.now(), self.TIME_FORMAT))
        try:
            logs = self.mongo_db[log['hive_id']].find({'type':'log'})
            data = []
            targets = []
            for log in logs:
                start = log['time']
                end = log['time'] - timedelta(hours = 1) #! set to next log entry
                samples = self.mongo_db[log['hive_id']].find({'type':'sample', 'time':{'$gt':end, '$lt':start}})
                for sample in samples:
                    params = [sample['int_t'], sample['ext_t']]
                    state = int(log['health'])
                    data.append(params)
                    targets.append(state)
            self.svc_health.fit(data, targets)
            print('\tOKAY')
        except Exception as error:
            print('\tERROR: %s' % str(error))
        
    ## Query Samples in Range to JSON-file
    def query_samples(self, hours):
        print('[Querying Samples in Range] %s' % datetime.strftime(datetime.now(), self.TIME_FORMAT))
        print('\tRange: ' + str(hours))
        time_range = datetime.now() - timedelta(hours = hours) # get datetime
        with open(self.DATA_PATH + 'samples.json', 'w') as jsonfile:
            result = []
            for name in self.mongo_db.collection_names():
                if not name == 'system.indexes':
                    # Add filters here to only include average values
                    for sample in self.mongo_db[name].find({'type':'sample', 'time':{'$gt': time_range, '$lt':datetime.now()}}):
                        sample['time'] = datetime.strftime(sample['time'], self.TIME_FORMAT)
                        result.append(sample)
            dump = json_util.dumps(result, indent=4)
            jsonfile.write(dump)
            
    ## Query Logs in Range to JSON-file
    def query_logs(self, hours):
        print('[Querying from Mongo] %s' % datetime.strftime(datetime.now(), self.TIME_FORMAT))
        print('\tTime Range: %s hours' % str(hours))
        time_range = datetime.now() - timedelta(hours = hours) # get datetime
        with open(self.DATA_PATH + 'logs.json', 'w') as jsonfile:
            result = []
            for name in self.mongo_db.collection_names():
                if not name == 'system.indexes':
                    for log in self.mongo_db[name].find({'type':'log', 'time':{'$gt': time_range, '$lt':datetime.now()}}):
                        log['time'] = datetime.strftime(log['time'], self.TIME_FORMAT)
                        result.append(log)
            dump = json_util.dumps(result, indent=4)
            jsonfile.write(dump)
    
    ## Dump to CSV
    def dump_csv(self, hours):
        print('\n[Dumping to CSV] %s' % datetime.strftime(datetime.now(), self.TIME_FORMAT))
        print('\tRange: %s' % str(hours))
        time_range = datetime.now() - timedelta(hours = hours) # get datetime
        with open(self.DATA_PATH + 'samples.csv', 'w') as csvfile:
            csvfile.write(','.join(self.ALL_PARAMETERS)) # Write headers
            for name in self.mongo_db.collection_names():
                    if not name == 'system.indexes':
                        for sample in self.mongo_db[name].find({'type':'sample', 'time':{'$gt': time_range, '$lt':datetime.now()}}):
                            sample['time'] = datetime.strftime(sample['time'], self.TIME_FORMAT)
                            sample_as_list = []
                            for param in self.ALL_PARAMETERS:
                                try:
                                    sample_as_list.append(str(sample[param]))
                                except Exception as error:
                                    print('ERROR: %s' % str(error))
                                    sample_as_list.append('NaN') # Not-a-Number if missing
                            sample_as_list.append('\n')
                            try:
                                csvfile.write(','.join(sample_as_list))
                            except Exception as error:
                                print('ERROR: %s' % str(error))
       
    ## Receive Sample
    def receive_sample(self):
        print('[Receiving Sample from Hive] %s' % datetime.strftime(datetime.now(), self.TIME_FORMAT))
        try:
            packet = self.socket.recv()
            sample = json.loads(packet)
            print('\tOKAY: %s' % str(sample))
            return sample
        except Exception as error:
            print('\tERROR: %s' % str(error))
            
    ## Store to Mongo
    def store_sample(self, sample):
        print('[Storing Sample] %s' % datetime.strftime(datetime.now(), self.TIME_FORMAT))
        try:
            sample['time'] = datetime.now()
            hive = self.mongo_db[sample['hive_id']]
            sample_id = hive.insert(sample)
            print('\tOKAY: %s' % str(sample_id))
            return str(sample_id)
        except Exception as error:
            print('\tERROR: %s' % str(error))
                        
    ## Classify
    def classify_sample(self, sample):
        print('[Classifying Sample] %s' % datetime.strftime(datetime.now(), self.TIME_FORMAT))
        try:
			try:
				health_data = [sample[v] for v in self.HEALTH_PARAMETERS]
				health = self.svc_health.predict(health_data)
			except Exception as error:
				health = None
				print('\tERROR: %s' % str(error))
			try:
				activity_data = [sample[v] for v in self.ACTIVITY_PARAMETERS]
				activity = self.svc_activity.predict(actvity_data)
			except Exception as error:
				activity = None
				print('\tERROR: %s' % str(error))
			try:
				environment_data = [sample[v] for v in self.ENVIRONMENT_PARAMETERS]
				environment = self.svc_environment.predict(environment_data)
			except Exception as error:
				environment = None
				print('\tERROR: %s' % str(error))
			estimators = {
				'health' : health,
				'environment' : environment,
				'activity' : activity
			}
			print('\tOKAY: %s' % str(estimators))
        except Exception as error:
            estimators = {}
            print('\tERROR: %s' % str(error))
        return estimators
            
    ### Send Response
    def send_response(self, estimators, sample_id):
        print('[Sending Response to Hive] %s' % datetime.strftime(datetime.now(), self.TIME_FORMAT))
        try:
            response = {
                'id' : sample_id,
                'type' : 'response',
                'time' : datetime.strftime(datetime.now(), self.TIME_FORMAT),
                'estimators' : estimators
                }
            dump = json.dumps(response)
            self.socket.send(dump)
            print('\tOKAY: %s' % str(response))
        except Exception as error:
            print('\tERROR: %s' % str(error))   
    
    """
    Periodic Functions
    """
    ## Listen for Next Sample
    def listen(self):
        print('\n----------- Listening for Nodes -----------')
        sample = self.receive_sample()
        sample_id = self.store_sample(sample)
        estimators = self.classify_sample(sample)
        self.send_response(estimators, sample_id)
        
    ## Compute Periodic Class
    def cluster(self):
        print('\n----------- Clustering Data -----------')
        
    
    """
    Handler Functions
    """
    ## Render Index
    @cherrypy.expose
    def index(self):
        print('\n----------- Loading Index Page -----------')
        html = open('static/index.html').read()
        return html
    
    ## Handle Posts
    @cherrypy.expose
    def default(self, *args, **kwargs):
        print('\n----------- Received POST Request -----------')
        try:
            print('\tPOST: %s' % str(kwargs))
            if kwargs['type'] == 'log':
                self.store_sample(kwargs)
                self.train_estimators(kwargs)
            elif kwargs['type'] == 'graph':
                self.query_samples(int(kwargs['range_select']))
            elif kwargs['type'] == 'save':
                self.dump_csv(int(kwargs['range_select']))
        except Exception as err:
            print('\tERROR: %s' % str(err))
        return None
    
# Main
if __name__ == '__main__':
    aggregator = HiveAggregator(CONFIG_FILE)
    cherrypy.server.socket_host = aggregator.CHERRYPY_ADDR
    cherrypy.server.socket_port = aggregator.CHERRYPY_PORT
    currdir = os.path.dirname(os.path.abspath(__file__))
    conf = {
        '/': {'tools.staticdir.on':True, 'tools.staticdir.dir':os.path.join(currdir,'static')},
        '/data': {'tools.staticdir.on':True, 'tools.staticdir.dir':os.path.join(currdir,'data')}, # NEED the '/' before the folder name
    }
    cherrypy.quickstart(aggregator, '/', config=conf)
