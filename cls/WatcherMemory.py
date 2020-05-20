#!/usr/bin/env python

import logging
import time

class MemoryObj():
    """ This is Object instance. It stores all detected location of this object
    """
    def __init__(self, detected_obj):
        self.data = [] # list of all matched objects
        self.append_data(detected_obj)
        self.triggered_actions = [] # list of triggered actions for this object
        #self.missed_cnt = 0 # how many times, this object was not detected in last checks
        self.time_last = time.time() # the last time object was detected
        #dict.__init__(self, triggered_actions=self.triggered_actions)

    def search_locations(self, detected_obj):
        """ Search in all locations, if location was already added
        """
        for mem_obj in self.data:
            if not mem_obj.get('box') == detected_obj.get('box'):
                return True
        return False

    def append_data(self, detected_obj):
        """ Adds new <detected_obj> to the <data> list, if it is not already present there.
        Returns: True if object has been append to the list
        """
        if not self.search_locations(detected_obj):
            self.data.append(detected_obj)
            return True
        return False

    def set_action_triggered(self, action_name):
        """ Will remember that given <action_name> was triggered"""
        self.triggered_actions.append(action_name)

    def is_action_triggered(self, action_name):
        """ Returns True if <action_name> was already triggered"""
        for name in self.triggered_actions:
            if name == action_name:
                return True
        return False

class WatcherMemory():
    """ Remember and forget each detected object.
    Incoming parameter: is a object detection result, which contains a list of detected objects
    Result: Check if at least one of the objects is not exists in memory
    Stages:
    - check each object if it is new
    - add object into memory or update timestamp
    - forget objects on timeout {memory_remember_time}
    """

    def __init__(self, cnfg, name):
        self.cnfg = cnfg
        self.name = name # name of the instance
        self.memory_data = []
        self.logger = logging.getLogger(f"{name}:WatcherMemory")

    def is_needed_to_remeber(self, detected_obj):
        """ Function check, if specifyed object is to remeber
        """
        if len(self.cnfg.memory_objects)>0:
            for obj_label in self.cnfg.memory_objects:
                if obj_label == detected_obj['class']:
                    break
                return False
        # check list of objects to exclude
        for obj_label in self.cnfg.memory_objects_exclude:
            if obj_label == detected_obj['class']:
                return False
        return True

    def add(self, data):
        """Function to add new object into memory. It checks if such object already exists.
        Returns: True, if it is a really new object (or existing object with no triggered actions yet)
        othervice returns False.
        <data> parameter can be a result of detection containing multiple objects,
        or can be object itself
        """
        if self.cnfg.memory_remember_time < 0:
            # If there is no need to remember then always return true
            return True
        objects = data.get('objects')
        if isinstance(objects, list):
            self.logger.debug("Remember detected objects list: '%s'", str(objects))
            # recursively add objects in list
            res = False
            for obj in objects:
                res = res or self.add(obj)
            self.cleanup()
            return res
        else:
            # check if it is needed to remember this object class
            if not self.is_needed_to_remeber(data):
                # return without memory, with a result that no new object was added
                return False
            # Search if object is already in memory
            mem_obj = self.search(data)
            if mem_obj is None:
                mem_obj = MemoryObj(data)
                data["is_in_memory"] = False
                data["memory_obj"] = mem_obj
                self.memory_data.append(mem_obj)
                self.logger.debug("Remember object: '%s'", str(data))
                return True
            else:
                data["is_in_memory"] = True
                data["triggered_actions"] = mem_obj.triggered_actions
                data["memory_obj"] = mem_obj
                mem_obj.append_data(data)
                if len(mem_obj.triggered_actions) > 0:
                    return True
        return False

    def search(self, detection_obj):
        """Function to search inside all memory objects for a new detected object.
        On succeed MemotyObj is returned, othervice returned None"""        
        for mem_obj in self.memory_data:
            self.logger.debug("search('%s') in %s", detection_obj, mem_obj.data)
            for obj in mem_obj.data:
                if self.compare_objects(obj, detection_obj):
                    mem_obj.time_last = time.time() # refresh time
                    self.logger.debug("Object found in memory: %s", detection_obj)
                    return mem_obj
        return None

    def calculate_intersection(self, rect_1, rect_2):
        """ Function calculates the intersection area between 2 rectangles
        Returns: % of intersection compared to <rect_1>
        """
        dx = min(rect_1[2], rect_2[2]) - max(rect_1[0], rect_2[0])
        dy = min(rect_1[3], rect_2[3]) - max(rect_1[1], rect_2[1])
        if (dx>=0) and (dy>=0):
            area_intersection = dx*dy
            area_original = abs((rect_1[2]-rect_1[0])*(rect_1[3]-rect_1[1]))
            return 100*area_intersection/area_original
        else:
            return 0

    def calculate_move(self, rect_1, rect_2):
        """ Function calculates shift between centers of rectangles
        Returns: value in pixels
        """
        try:
            dx = abs((rect_1[2]-rect_1[0])/2 - (rect_2[2]-rect_2[0])/2)
            dy = abs((rect_1[3]-rect_1[1])/2 - (rect_2[3]-rect_2[1])/2)
            return max(dx, dy)
        except ZeroDivisionError:
            self.logger.debug("ZeroDivisionError: %s | %s", rect_1, rect_2)
            return 0

    def calculate_size_change(self, rect_1, rect_2):
        """ Function calculates the average change in height and width
        Returns: % from <rect_1> values
        """
        try:
            dx = 100 * abs((rect_1[2]-rect_1[0]) - (rect_2[2]-rect_2[0]))/(rect_1[2]-rect_1[0])
            dy = 100 * abs((rect_1[3]-rect_1[1]) - (rect_2[3]-rect_2[1]))/(rect_1[3]-rect_1[1])
            return (dx + dy) / 2
        except ZeroDivisionError:
            self.logger.debug("ZeroDivisionError: %s | %s", rect_1, rect_2)
            return 0

    def compare_objects(self, obj1, obj2):
        """ Function return True if objects are similar
        """
        try:
            if obj1.get('class') == obj2.get('class'):
                obj1_shape = obj1.get('box', [0,0,0,0])
                obj2_shape = obj2.get('box', [0,0,0,0])
                if self.calculate_intersection(obj1_shape, obj2_shape) >= self.cnfg.memory_area_intersect \
                    or self.calculate_size_change(obj1_shape, obj2_shape) >= self.cnfg.memory_size_similarity \
                    or self.calculate_move(obj1_shape, obj2_shape) < self.cnfg.memory_move_threshold:
                    #self.logger.debug("compare_objects TRUE: %s || %s", obj1, obj2)
                    return True
                #self.logger.debug("compare_objects FALSE: %s || %s", obj1, obj2)
            return False
        except Exception as ex:
            self.logger.exception("compare_objects() failed")
            raise ex
        return False

    def cleanup(self):
        """Remove(forget) all outdated objects from memory"""
        for obj in self.memory_data:
            if time.time() - obj.time_last > self.cnfg.memory_remember_time:
                self.memory_data.remove(obj)
                self.logger.debug("Forget object (timeout): '%s'", obj)

