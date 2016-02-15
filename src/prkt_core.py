import rospy

from copy import deepcopy
from geometry_msgs.msg import Twist
from matrix import inverse, transpose, mm
from nav_msgs.msg import Odometry
from random import random
from utils import version
from viz_feature_sim.msg import Observation

import numpy.random.normal as normal # normal(mu, sigma, count)

class SlamAlgorithm(object):
    def __init__(self):
        pass

    def motion_update(self, twist):
        pass

    def motion_model(self, prevState, twist, dt):
        return self.motion_model_noisy(prevState, twist, dt)

    def motion_model_noisy(self, prevState, twist, dt):
        # pS      h1        |
        # 0-----------------0
        # |                 h2
        dheading = twist.twist.angular.z * dt
        
        drive_noise = normal(0, .05, 1)
        ds = twist.twist.linear.x * dt

        prev_x = prevState.pose.pose.position.x
        prev_y = prevState.pose.pose.position.y
        prev_heading = quaternion_to_heading(prevState.pose.pose.orientation)

        heading_noise = normal(0, .05, 1)
        heading_1 = prev_heading+dheading/2+heading_noise

        heading_noise = normal(0, .05, 1)
        heading_2 = heading_1+dheading/2+heading_noise

        dx = ds*math.cos(heading_1)
        dy = ds*math.cos(heading_1)

        prevState.pose.pose.position.x += dx
        prevState.pose.pose.position.y += dy
        prevState.pose.pose.orientation = heading_to_quaternion(heading_2)

        return prevState

    def motion_model_noise_free(self, prevState, twist, dt):
        # for reference
        # pS      h1        |
        # 0-----------------0
        # |                 h2
        dheading = twist.twist.angular.z * dt
        ds = twist.twist.linear.x * dt
        prev_x = prevState.pose.pose.position.x
        prev_y = prevState.pose.pose.position.y
        prev_heading = quaternion_to_heading(prevState.pose.pose.orientation)

        heading_1 = prev_heading+dheading/2
        heading_2 = prev_heading+dheading
        dx = ds*math.cos(heading_1)
        dy = ds*math.cos(heading_1)

        prevState.pose.pose.position.x += dx
        prevState.pose.pose.position.y += dy
        prevState.pose.pose.orientation = heading_to_quaternion(heading_2)

        return prevState

class ParticleMixedSlam(SlamAlgorithm):
    '''
    Need to combine 3 measurements to get an initial estimate for the pose of the landmark
     Use this in combination with maintaining new landmark hypothesis to start adding landmarks
     When they are ready to be added, initialize a gaussian based on the first triangulation
     Then use this to start measuring the likelihood of a new measurement corresponding to that landmark

    To trim down the number of landmarks that need to be scanned, create a graph of landmarks
     On this graph, connect landmarks that have been seen together before. When searching for landmarks,
     do a graph traversal starting from the initial pose out, stopping at some number of nodes on the graph
     Potentially weight edges with the number of times that two features have been seen together

    In small cases, this will just search all of the nodes, eventually with lots of data it should limit
     the correspondence to new nodes and nodes that are close together
    '''

    def __init__(self):
        # particle = individiual state estimate + 1 kalman filter per map feature (total of N)
        # Particle filter: M particles
        self.M = 10
        self.robot_particles = []
        self.initialize_particle_filter()
        
        self.hypothesis_features = []
        
        self.last_time = rospy.Time.now()
        self.last_twist = Twist()

    @version(0,2,0)
    def initialize_particle_filter(self):
        for _ in range(0,int(self.M)):
            self.robot_particles.append(RobotParticle(0,0.1))

    @version(0,2,0)
    def motion_update(self, twist):
        new_time = rospy.time.now()
        dt = new_time - self.last_motion_update_time
        for particle in self.robot_particles:
            particle.state = motion_model(particle.state, self.last_control, dt)
        self.last_motion_update_time = new_time
        self.last_control = twist

    @version(0,2,0)
    def measurement_update(self, measurement):
        if is_instance(measurement, Observation):
            self.cam_observation_update(measurement)
        else:
            pass

    # @version(0,2,0)
    # def condense_robot_state(self):
    #     avg_state = 0

    @version(0,2,0)
    def cam_observation_model(self, cam_obs):
        '''Single bearing-color observation'''
        zt = cam_obs

        self.motion_update(self.last_twist)

        for particle in particle_list:
            j = particle.get_feature_id(zt)
            if j < 0: # not seen before
                new_mean = self.inverse_measurement_model(particle.state, zt)
                H = self.jacobian_linearization_of_motion_model(particle.state, new_mean)
                H_inverse = inverse(H)
                new_covar = mm(mm(H_inverse, Qt), transpose(H_inverse))
                particle.add_new_feature_ekf(new_mean, new_covar)
                particle.weight = particle.default_weight()
            else: # j seen before
                old_measurement_ekf = particle.get_feature_by_id(j)
                z_hat = particle.measurement_prediction(old_measurement_ekf.mean, particle.state)
                H = jacobian_linearization_of_motion_model(particle.state, old_measurement_ekf.mean)
                Q = mm(mm(H, old_measurement_ekf.covar), transpose(H)) + Qt
                Q_inverse = inverse(Q)
                K = mm(mm(old_measurement_ekf.covar, transpose(H)), Q_inverse)

                new_mean = old_measurement_ekf.mean + mm(K, zt - z_hat)
                new_covar = mm(identity(5,5) - mm(K, H), old_measurement_ekf.covar)

                particle.replace_feature_ekf(j, new_mean, new_covar)
                particle.weight = pow(2*pi*magnitude(Q), -1/2) * exp(-0.5 * (transpose(zt - z_hat)*Q_inverse*(zt - z_hat)))
            # endif
            # for all other features...do nothing
        # end for
        
        temp_particle_list = []
        sum_ = 0
        for particle in particle_list:
            sum_ = sum_ + particle.weight

        chosen = random()*sum_

        for _ in range(0, len(particle_list)):
            for particle in particle_list:
                chosen = chosen - particle.weight
                if chosen < 0:
                    # choose this particle
                    new_particle_list.append(particle.deep_copy())

        particle_list = temp_particle_list

@version(0,2,0)
class RobotParticle(Odometry):
    def __init__(self, mean, distribution):
        self.pose.pose.position.x = mean + normal(0,distribution)
        self.pose.pose.position.y = mean + normal(0,distribution)

        self.feature_models = []
        self.N = len(self.feature_models)
        self.weight = 0
        self.state = self

    def add_new_feature_ekf(self, mean, covar):
        # TODO(bucbkasin):
        pass

    def replace_feature_ekf(self, feature_id, mean, covar):
        # TODO(bucbkasin):
        pass

    def get_feature_id(self, measurement):
        # TODO(bucbkasin): may replace this method
        # for now, return < 0 for a new particle
        pass

    def get_feature_by_id(self, feature_id):
        # TODO(bucbkasin): may replace this method
        pass

    def default_weight(self):
        # TODO(buckbaskin):
        return 0.5

    def deep_copy(self):
        return deepcopy(self)


class FeatureModel(object):
    def __init__(mean, covar):
        '''
        gaussian model of a feature state (x, y, r, g, b)
        '''
        self.x = mean[0]
        self.y = mean[1]
        self.r = mean[2]
        self.g = mean[3]
        self.b = mean[4]
        self.mean_array = mean[0:5]
        for i in range(0,5):
            covar[i] = covar[i][0:5]
        self.covar_matrix = covar[0:5]

    def mean(self):
        return [self.x, self.y, self.r, self.g, self.b]

    def covar(self):
        return self.covar_matrix