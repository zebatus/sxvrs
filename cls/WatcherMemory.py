#!/usr/bin/env python

import os, logging
import time

class memory_obj():
    def __init__(self, data):
        self.data = data
        self.time_last = time.time()

class WatcherMemory():
    """ Remember and forget each detected object.
    - check if object is new
    - add object into memory
    - forget objects on timeout
    """

    def __init__(self, cnfg, name):
        self.cnfg = cnfg
        self.name = name # name of the instance
        self.memory_data = []
        self.logger = logging.getLogger(f"{name}:WatcherMemory")

    def add(self, data):
        """Function to add new object into memory. It checks if such object already exists. 
        returns True, if new object added, othervice returns False
        """
        if self.cnfg.memory_remember_time<0:
            # If there is no need to remember then always return true
            return True
        objects = data.get('objects')
        if isinstance(objects, list):
            # recursively add objects in list
            res = False
            for obj in objects:
                res = res or self.add(obj)
            self.cleanup()
            return res
        else:
            # check if object is already in memory
            if not self.check(data):
                obj = memory_obj(data)
                self.memory_data.append(obj)
                self.logger.debug(f"Remember object: '{str(data)}'")
                return True
            else:
                return False

    def check(self, data):
        """Function to search memory for object"""
        res = False
        try:
            data_shape = data.get('box', [0,0,0,0])
            h0 = (data_shape[0] - data_shape[2])
            w0 = (data_shape[1] - data_shape[3])
            for obj in self.memory_data:
                if obj.data.get('class') == data.get('class'):
                    obj_shape = obj.data.get('box', [0,0,0,0])
                    h1 = (obj_shape[0] - obj_shape[2])
                    w1 = (obj_shape[1] - obj_shape[3])
                    res =         (abs(h0-h1)/max(h0,h1) < self.cnfg.memory_move_threshold)
                    res = res and (abs(w0-w1)/max(w0,w1) < self.cnfg.memory_move_threshold)
                    res = res and (abs(obj_shape[0] - data_shape[0])/max(h0,h1) < self.cnfg.memory_move_threshold)
                    res = res and (abs(obj_shape[2] - data_shape[2])/max(h0,h1) < self.cnfg.memory_move_threshold)
                    res = res and (abs(obj_shape[1] - data_shape[1])/max(w0,w1) < self.cnfg.memory_move_threshold)
                    res = res and (abs(obj_shape[3] - data_shape[3])/max(w0,w1) < self.cnfg.memory_move_threshold)
                    self.logger.debug(f"Checki obj in memory: {res}: {obj.data} || {data}")
                    if res:
                        obj.time_last = time.time() # refresh time
                        self.logger.debug(f"Object found in memory: {data}")
                        break
        except ZeroDivisionError:
            self.logger.debug(f"ZeroDivisionError: {data}")
        except Exception as e:
            self.logger.exception(f"check() failed")
            raise e
        return res

    def cleanup(self):
        """Remove(forget) all outdated objects from memory"""
        for obj in self.memory_data:
            if time.time() - obj.time_last > self.cnfg.memory_remember_time:
                self.memory_data.remove(obj)
                self.logger.debug(f"Forget object: '{obj}'")

