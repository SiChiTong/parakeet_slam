#!/usr/bin/env python

'''
Create a ROS node that uses the parakeet core to do SLAM
'''

import rospy
import sys

from geometry_msgs.msg import Twist
from matrix import Matrix
from nav_msgs.msg import Odometry
from prkt_core_v2 import FastSLAM, Feature
from utils import quaternion_to_heading, heading_to_quaternion
from viz_feature_sim.msg import VizScan

class CamSlam360(object):
    '''
    Maintains a state for the robot, as well as for features
    Robot state:
    v1: x, y, heading, v (linear, x), w (angular, z)
    Feature state:
    v1: x, y, r, g, b
    '''
    def __init__(self):
        rospy.init_node('CAMSLAM360')
        # prepare filter

        self.core = None

        preset_covariance = Matrix([[.01,0,0,0,0],
                                    [0,.01,0,0,0],
                                    [0,0,.01,0,0],
                                    [0,0,0,.01,0],
                                    [0,0,0,0,.01]])

        # purple, origin
        feature1 = Feature(mean=Matrix([0,0,161,77,137]), covar=preset_covariance)
        feature1.__immutable__ = True
        # blue
        feature2 = Feature(mean=Matrix([10,0,75,55,230]), covar=preset_covariance)
        feature2.__immutable__ = True
        # green
        feature3 = Feature(mean=Matrix([0,15,82,120,68]), covar=preset_covariance)
        feature3.__immutable__ = True
        # pink
        feature4 = Feature(mean=Matrix([10,15,224,37,192]), covar=preset_covariance)
        feature4.__immutable__ = True

        features = [feature1, feature2, feature3, feature4]

        self.initialize_particle_filter(features)

        # begin ros updating
        self.cam_sub = rospy.Subscriber('/camera/features', VizScan,
            self.measurement_update)
        self.twist_sub = rospy.Subscriber('/cmd_vel', Twist, self.motion_update)

        self.odom_pub = rospy.Publisher('/slam_estimate', Odometry, queue_size=1)
    
    def run(self):
        if self.core is not None:
            rospy.loginfo('Running!')
            self.print_summary()
            rospy.spin()

    def initialize_particle_filter(self, preset_features):
        '''
        Create an instance of FastSLAM algorithm
        '''
        self.core = FastSLAM(preset_features)

    def easy_odom(self):
        x, y, heading = self.core.summary()
        otto = Odometry()
        otto.header.frame_id = 'odom'
        otto.header.stamp = rospy.Time.now()
        otto.pose.pose.position.x = x
        otto.pose.pose.position.y = y
        otto.pose.pose.orientation = heading_to_quaternion(heading)
        return otto

    def measurement_update(self, msg):
        '''
        Pass along a VizScan message
        '''
        self.core.cam_cb(msg)
        # self.print_summary()
        odom = self.easy_odom()
        self.odom_pub.publish(odom)

    def motion_update(self, msg):
        '''
        Pass along a Twist message
        '''
        # rospy.loginfo('motion_update('+str(msg)+')')
        self.core.motion_update(msg)
        # self.print_summary()
        odom = self.easy_odom()
        self.odom_pub.publish(odom)

    def print_summary(self):
        '''
        average x, y, heading
        '''
        rospy.loginfo('prkt_summary: '+str(self.core.summary()))


if __name__ == '__main__':
    cs = CamSlam360()
    cs.run()
