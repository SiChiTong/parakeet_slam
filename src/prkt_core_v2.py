'''
Parakeet-Core

This is the Python module that implements the SLAM algorithm for use in a ROS
node.

# Matrices are rows by columns
'''

# pylint: disable=invalid-name
# pylint: disable=no-self-use

import rospy
import math
import numpy as np

from copy import deepcopy
from geometry_msgs.msg import Twist
from matrix import inverse, transpose, mm, identity, magnitude, madd, msubtract
from matrix import blob_to_matrix
from nav_msgs.msg import Odometry
from numpy.random import normal
from random import random
from utils import version, heading_to_quaternion, quaternion_to_heading
from viz_feature_sim.msg import VizScan, Blob

class FastSLAM(object):
    def __init__(self):
        self.last_control = Twist()
        self.last_update = rospy.Time.now()
        self.particles = [FilterParticle(), FilterParticle()]
        self.Qt = Matrix([[1, 0], [0, 1]]) # measurement noise?

    def cam_cb(self, scan):
        # motion update all particles
        self.motion_update(self.last_control)

        for particle in self.particles:
            particle.weight = 1
            correspondence = particle.match_features_to_scan(scan)
            for pair in correspondence:
                blob = pair[1]
                if pair[0] < 0:
                    # new feature observed
                    particle.add_hypothesis(particle.state, blob)
                    particle.weight *= particle.no_match_weight()
                else:
                    # existing feature observed
                    # generate expected measurement based on feature id
                    pseudoblob = particle.generate_measurement(pair[0])
                    bigH = particle.measurement_jacobian(pair[0])
                    bigQ = particle.measurement_covariance(bigH, pair[0], self.Qt)
                    bigQinv = inverse(bigQ)
                    bigK = particle.kalman_gain(pair[0], bigH, bigQinv)

                    (particle.get_feature_by_id(pair[0])
                        .update_mean(bigK, blob, pseudoblob))
                    (particle.get_feature_by_id(pair[0])
                        .update_covar(bigK, bigH))

                    weighty = particle.importance_factor(bigQ, blob, pseudoblob)
                    particle.weight *= weighty

        self.low_variance_resample()


    def odom_motion_update(self, odom):
        '''
        ***Alpha feature***
        update particles by looking at the change in odometry as the motion
        model
        '''
        pass

    def motion_update(self, new_twist):
        '''
        update the state of all of the particles by the given twist
        input:
            new_twist: twist for the next motion
        output:
            None
        '''

        twist = self.last_control
        dt = rospy.Time.now() - self.last_update
        for i in range(0, len(self.particles)):
            self.particles[i] = motion_model(self.particles[i], self.last_control, dt)

        self.last_update = self.last_update + dt
        self.last_control = new_twist

    def motion_model(self, particle, twist, dt):
        # pS      h1        |
        # 0-----------------0
        # |                 h2
        v = twist.linear.x
        w = twist.angular.z

        new_particle = FilterParticle()
        new_particle.feature_set = deepcopy(particle.feature_set)

        dheading = twist.twist.angular.z * dt

        drive_noise = normal(0, .05*v+.01*w, 1)
        ds = twist.twist.linear.x * dt + drive_noise

        prev_heading = quaternion_to_heading(particle.pose.pose.orientation)

        heading_noise = normal(0, .05*w+.01*v, 1)
        heading_1 = prev_heading+dheading/2+heading_noise

        heading_noise = normal(0, .05*w+.01*v, 1)
        heading_2 = heading_1+dheading/2+heading_noise

        dx = ds*math.cos(heading_1)
        dy = ds*math.cos(heading_1)

        new_particle.state.pose.pose.position.x += dx
        new_particle.state.pose.pose.position.y += dy
        new_particle.state.pose.pose.orientation = heading_to_quaternion(heading_2)

        return new_particle

    def low_variance_resample(self):
        '''
        Resample particles based on weights
        '''
        sum_ = reduce(lambda accum, element: accum+element.weight, self.particles, 0.0)
        range_ = sum_/float(len(self.particles))
        step = random()*range_
        temp_particles = []
        count = 0

        ### resample ###

        for particle in self.particles:
            step = step - particle.weight
            while step <= 0.0 and count < len(self.particles):
                # add it to the list
                temp_particles.append(deepcopy(particle))
                # do I need the deepcopy? 
                #   If the motion model creates a new particle, no
                
                # take a step forward
                step += range_
                count += 1
                # repeat if its still in the particle range

        self.particles = temp_particles


class FilterParticle(object):
    def __init__(self, state=Odometry()):
        self.state = state
        self.feature_set = {}

    def get_feature_by_id(self, id_):
        '''
        get the feature by id
        currently, if there is no feature for that id, it raises an error
        input:
            int (feature)id_
        output:
            Feature
        raises:
            KeyError
        '''
        return self.feature_set[id_]

    def match_features_to_scan(self, scan):
        '''
        Version 1: independently match each scan to the most likely feature
        Version 2: match each scan to a unique feature 
            (if they are sufficiently far apart)
        Version 3: graph based enhanced lookup
            Use a graph of features that have been seen together to speed up the
            search for features that are likely to be seen
            Might be: run v1, then take the most likely, and search from there
            for features to match
        input:
            VizScan scan
        output:
            list of tuples mapping feature ids to Blobs
            negative numbers = new feature
        '''
        # TODO(buckbaskin):
        johndoe = []
        johndoe.append((-1, Blob()))
        johndoe.append((-2, scan.observes[0]))
        return johndoe

    def add_hypothesis(self, state, blob):
        '''
        add a hypothetical new feature to the non-invertable measurement model
        check to see if it matches a hypothetical feature. If that hypothetical
        is strong enough, add it to the particles
        input:
            Odometry state (position of observation)
            Blob blob (observation)
        output:
            None
        '''
        # TODO(buckbaskin):
        pass

    def measurement_jacobian(self, feature_id):
        '''
        Calculate the Jacobian of the measurement model with respect to the
        current particle state and the give feature's mean

        bigH is the Jacobian of the measurement model with respect to the best
        estimate of the robot's position at the time of the update (computed at 
        the mean of the feature, aka the predicted mean) PR p. 207

        input:
            int feature_id
        output:
            np.ndarray 4x3 (bigH)
        '''
        '''
        State = { x, y, heading } = [x , y, heading (theta)]
        measurements = { bearing, r, g, b} = [bearing (phi), r, g, b]

        Jacobian = 
        [[d phi/d x, d phi/d y, d phi/d theta],
         [d r/d x,   d r/d y,   d r/d theta  ],
         [d g/d x,   d g/d y,   d g/d theta  ],
         [d b/d x,   d b/d y,   d b/d theta  ]]
        '''
        state = self.state
        mean_x = state.pose.pose.position.x
        mean_y = state.pose.pose.position.y
        feature_mean = self.get_feature_by_id(feature_id).mean
        feature_x = feature_mean.x
        feature_y = feature_mean.y
        
        # phi = atan2(dy, dx) - heading
        # q = (feature_x - mean_x)^2 + (feature_y - mean_y)^2
        q = pow(feature_x - mean_x, 2) + pow(feature_y - mean_y, 2)

        # d_phi/d_x = (feature_y - mean_y) / q
        d_phi_d_x = (feature_y - mean_y) / q
        
        # d_phi/d_y = (feature_x - mean_x) / q
        d_phi_d_y = (feature_x - mean_x) / q

        # d_phi/d_theta = -1
        d_phi_d_theta = -1.0

        return Matrix([[d_phi_d_x, d_phi_d_y, d_phi_d_theta],
                         [0.0, 0.0, 0.0],
                         [0.0, 0.0, 0.0],
                         [0.0, 0.0, 0.0]])

    def measurement_covariance(self, bigH, feature_id, Qt):
        '''
        Calculate the covarance of the measurement with respect to the given
        Jacobian bigH, the feature's covariance and Qt (measurement noise?)
        input:
            np.ndarray bigH (Jacobian of the measurement model)
            int feature_id
            np.ndarray Qt (measurement noise)
        output:
            numpy.ndarray
        '''
        old_covar = self.get_feature_by_id(feature_id).covar
        return numpy.array(madd(mm(mm(bigH , old_covar) , transpose(bigH)) , Qt))

    def kalman_gain(self, feature_id, bigH, Qinv):
        '''
        Calculate the kalman gain for the update of the feature based on the
        existing covariance of the feature, bigH, and the inverse of bigQ
        input:
            int feature_id
            np.ndarray bigH (Jacobian of the measurement model)
            np.ndarray Qinv (inverse of Q, the measurement covariance)
        output:
            numpy.ndarray
        '''
        old_covar = self.get_feature_by_id(feature_id).covar
        return numpy.array(mm(mm(old_covar , transpose(bigH)) , Qinv))

    def importance_factor(self, bigQ, blob, pseudoblob):
        '''
        Calculate the relative importance of this measurement (weight) to be
        used as part of resampling
        Input:
            np.ndarray bigQ (measurement covariance)
            Blob blob (recieved measurement)
            Blob pseudoblob (estimated measurement)
        '''
        v1 = 2*math.pi *magnitude(bigQ)
        v1 = pow(v1, -0.5)
        delz = blob_to_matrix(blob) - blob_to_matrix(pseudoblob)
        delzt = transpose(delz)
        v2 = math.exp(-0.5 * mm(mm(delzt, inverse(bigQ)), delz))
        return v1 * v2

class Feature(object):
    def __init__(self, mean=None):
        if mean is None:
            mean = Matrix([0, 0, 0, 0, 0])
        if covar is None:
            covar = Matrix([[1, 0, 0, 0, 0],
                                [0, 1, 0, 0, 0],
                                [0, 0, 1, 0, 0],
                                [0, 0, 0, 1, 0],
                                [0, 0, 0, 0, 1]])
        self.mean = mean
        self.covar = covar
        self.identity = identity(covar.shape[0])

    def update_mean(self, kalman_gain, measure, expected_measure):
        '''
        Update the mean of a known feature based on the calculated Kalman gain
        and the different between the given measurement and the expected
        measurement
        input:
            np.ndarray kalman_gain
            np.ndarray measure(ment)
            np.ndarray expected_measure(ment)
        output:
            None
        '''
        delz = blob_to_matrix(measure) - blob_to_matrix(expected_measure)
        adjust = mm(kalman_gain, delz)
        self.mean = mean + adjust

    def update_covar(self, kalman_gain, bigH):
        '''
        Update the covariance of a known feature based on the calculated Kalman
        gain and the Jacobian of the measurement model (bigH)
        input:
            np.ndarray kalman_gain
            np.ndarray bigH
        output:
            None
        '''
        adjust = msubtract(self.identity, mm(kalman_gain, bigH))
        self.covar = mm(adjust, self.covar)
