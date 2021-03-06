#!/usr/bin/python
#-*- coding: utf-8 -*-

# >.>.>.>.>.>.>.>.>.>.>.>.>.>.>.>.
# Licensed under the Apache License, Version 2.0 (the "License")
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0

# --- File Name: loss_hd.py
# --- Creation Date: 07-04-2020
# --- Last Modified: Tue 21 Apr 2020 16:24:36 AEST
# --- Author: Xinqi Zhu
# .<.<.<.<.<.<.<.<.<.<.<.<.<.<.<.<
"""
HD disentanglement model losses.
"""

import numpy as np
import tensorflow as tf
import dnnlib.tflib as tflib
from dnnlib.tflib.autosummary import autosummary

def calc_vc_loss(delta_target, regress_out, C_global_size, D_lambda, C_lambda):
    # Continuous latents loss
    prob_C = tf.nn.softmax(regress_out, axis=1)
    I_loss_C = delta_target * tf.log(prob_C + 1e-12)
    I_loss_C = C_lambda * I_loss_C

    I_loss_C = tf.reduce_sum(I_loss_C, axis=1)
    I_loss = - I_loss_C
    return I_loss

def calc_cls_loss(discrete_latents, cls_out, D_global_size, C_global_size, cls_alpha):
    assert cls_out.shape.as_list()[1] == D_global_size
    prob_D = tf.nn.softmax(cls_out, axis=1)
    I_info_loss_D = discrete_latents * tf.log(prob_D + 1e-12)
    I_info_loss = cls_alpha * I_info_loss_D

    I_info_loss = tf.reduce_sum(I_info_loss, axis=1)
    I_info_loss = - I_info_loss
    return I_info_loss

def reparameterize(prior_traj_latents, minibatch_size):
    prior_traj_latents_mean, prior_traj_latents_logvar = tf.split(
        prior_traj_latents, num_or_size_splits=2, axis=1)
    eps_traj = tf.random.normal(shape=[minibatch_size, prior_traj_latents_mean.shape[1]])
    prior_traj_latents = eps_traj * tf.exp(prior_traj_latents_logvar * .5) + prior_traj_latents_mean
    return prior_traj_latents_mean, prior_traj_latents_logvar, prior_traj_latents

def log_normal_pdf(sample, mean, logvar, raxis=1):
      log2pi = tf.math.log(2. * np.pi)
      return tf.reduce_sum(
          -.5 * ((sample - mean) ** 2. * tf.exp(-logvar) + logvar + log2pi),
          axis=raxis)

def IandM_loss(I, M, G, opt, training_set, minibatch_size, I_info=None, latent_type='uniform',
               C_global_size=10, D_global_size=0, D_lambda=0, C_lambda=1, cls_alpha=0, epsilon=3,
               random_eps=False, traj_lambda=None, n_levels=None, resolution_manual=1024, use_std_in_m=False,
               model_type='hd_dis_model', hyperplane_lambda=1, prior_latent_size=512):
    _ = opt
    if D_global_size > 0:
        discrete_latents = tf.random.uniform([minibatch_size], minval=0, maxval=D_global_size, dtype=tf.int32)
        discrete_latents = tf.one_hot(discrete_latents, D_global_size)
        # discrete_latents_2 = tf.random.uniform([minibatch_size], minval=0, maxval=D_global_size, dtype=tf.int32)
        # discrete_latents_2 = tf.one_hot(discrete_latents_2, D_global_size)

    resolution_log2 = int(np.log2(resolution_manual))
    nd_out_base = C_global_size // (resolution_log2 - 1)
    nd_out_list = [nd_out_base + C_global_size % (resolution_log2 - 1) if i == 0 else nd_out_base for i in range(resolution_log2 - 1)]
    nd_out_list = nd_out_list[::-1]

    if latent_type == 'uniform':
        latents = tf.random.uniform([minibatch_size, C_global_size], minval=-2, maxval=2)
    elif latent_type == 'normal':
        latents = tf.random.normal([minibatch_size, C_global_size])
    elif latent_type == 'trunc_normal':
        latents = tf.random.truncated_normal([minibatch_size, C_global_size])
    else:
        raise ValueError('Latent type not supported: ' + latent_type)

    latents = autosummary('Loss/latents', latents)

    # Sample delta latents
    C_delta_latents = tf.random.uniform([minibatch_size], minval=0, maxval=sum(nd_out_list[:n_levels]), dtype=tf.int32)
    C_delta_latents = tf.cast(tf.one_hot(C_delta_latents, C_global_size), latents.dtype)

    if not random_eps:
        delta_target = C_delta_latents * epsilon
        # delta_latents = tf.concat([tf.zeros([minibatch_size, D_global_size]), delta_target], axis=1)
    else:
        epsilon = epsilon * tf.random.normal([minibatch_size, 1], mean=0.0, stddev=2.0)
        # delta_target = tf.math.abs(C_delta_latents * epsilon)
        delta_target = C_delta_latents * epsilon
        # delta_latents = tf.concat([tf.zeros([minibatch_size, D_global_size]), delta_target], axis=1)

    if D_global_size > 0:
        latents = tf.concat([discrete_latents, latents], axis=1)
        # delta_latents = tf.concat([discrete_latents_2, delta_latents], axis=1)
        delta_var_latents = tf.concat([tf.zeros([minibatch_size, D_global_size]), delta_target], axis=1)
    else:
        delta_var_latents = delta_target

    delta_latents = delta_var_latents + latents

    labels = training_set.get_random_labels_tf(minibatch_size)

    if model_type == 'hd_hyperplane':
        prior_traj_latents, orth_constraint = M.get_output_for(latents, is_training=True)
        prior_traj_delta_latents, orth_constraint_2 = M.get_output_for(delta_latents, is_training=True)
    else:
        prior_traj_latents = M.get_output_for(latents, is_training=True)
        prior_traj_delta_latents = M.get_output_for(delta_latents, is_training=True)
    if use_std_in_m:
        prior_traj_latents_mean, prior_traj_latents_logvar, prior_traj_latents = reparameterize(prior_traj_latents, minibatch_size)
        prior_traj_latents_mean = autosummary('Loss/prior_traj_latents_mean', prior_traj_latents_mean)
        prior_traj_latents_logvar = autosummary('Loss/prior_traj_latents_logvar', prior_traj_latents_logvar)
    prior_traj_latents = autosummary('Loss/prior_traj_latents', prior_traj_latents)
    if use_std_in_m:
        prior_traj_delta_latents_mean, prior_traj_delta_latents_logvar, prior_traj_delta_latents = reparameterize(prior_traj_delta_latents, minibatch_size)
    fake1_out = G.get_output_for(prior_traj_latents, labels, is_training=True, randomize_noise=True, normalize_latents=False)
    fake2_out = G.get_output_for(prior_traj_delta_latents, labels, is_training=True, randomize_noise=True, normalize_latents=False)
    fake1_out = autosummary('Loss/fake1_out', fake1_out)

    regress_out_list = I.get_output_for(fake1_out, fake2_out, is_training=True)
    regress_out = tf.concat(regress_out_list[:n_levels], axis=1)

    I_loss = calc_vc_loss(C_delta_latents[:,:sum(nd_out_list[:n_levels])], regress_out, C_global_size, D_lambda, C_lambda)
    I_loss = autosummary('Loss/I_loss', I_loss)

    if traj_lambda is not None:
        if not use_std_in_m:
            traj_reg = tf.reduce_sum(prior_traj_latents * prior_traj_latents, axis=1)
        else:
            logpz = log_normal_pdf(prior_traj_latents, 0., 0.)
            logqz_x = log_normal_pdf(prior_traj_latents,
                                     prior_traj_latents_mean, prior_traj_latents_logvar)
            traj_reg = logqz_x - logpz
        traj_reg = autosummary('Loss/traj_reg', traj_reg)
        I_loss = I_loss + traj_lambda * traj_reg

    if I_info is not None:
        cls_out = I_info.get_output_for(fake1_out, is_training=True)
        I_info_loss = calc_cls_loss(discrete_latents, cls_out, D_global_size, C_global_size, cls_alpha)
        I_info_loss = autosummary('Loss/I_info_loss', I_info_loss)
        I_loss = I_loss + I_info_loss
        I_loss = autosummary('Loss/I_loss_after_INFO', I_loss)

    return I_loss, None

def IandM_hyperplane_loss(I, M, G, opt, training_set, minibatch_size, I_info=None, latent_type='uniform',
               C_global_size=10, D_global_size=0, D_lambda=0, C_lambda=1, cls_alpha=0, epsilon=3,
               random_eps=False, traj_lambda=None, n_levels=None, resolution_manual=1024, use_std_in_m=False,
               model_type='hd_dis_model', hyperplane_lambda=1, prior_latent_size=512, hyperdir_lambda=1):
    _ = opt
    resolution_log2 = int(np.log2(resolution_manual))
    nd_out_base = C_global_size // (resolution_log2 - 1)
    nd_out_list = [nd_out_base + C_global_size % (resolution_log2 - 1) if i == 0 else nd_out_base for i in range(resolution_log2 - 1)]
    nd_out_list = nd_out_list[::-1]

    # Sample delta latents
    C_delta_latents = tf.random.uniform([minibatch_size], minval=0, maxval=sum(nd_out_list[:n_levels]), dtype=tf.int32)
    C_delta_latents = tf.cast(tf.one_hot(C_delta_latents, C_global_size), tf.float32)

    if not random_eps:
        delta_target = C_delta_latents * epsilon
    else:
        # epsilon = epsilon * tf.random.normal([minibatch_size, 1], mean=0.0, stddev=2.0)
        # delta_target = C_delta_latents * epsilon
        delta_target = C_delta_latents

    delta_var_latents = delta_target

    all_delta_var_latents = tf.eye(C_global_size, dtype=tf.float32)

    labels = training_set.get_random_labels_tf(minibatch_size)

    # Get variation direction in prior latent space.
    prior_var_latents, hyperplane_constraint = M.get_output_for(delta_var_latents, is_training=True)
    prior_all_dirs, _ = M.get_output_for(all_delta_var_latents, is_training=True)

    prior_var_latents = autosummary('Loss/prior_var_latents', prior_var_latents)
    manipulated_prior_dir = tf.matmul(prior_var_latents, tf.transpose(prior_all_dirs)) # [batch, C_global_size]
    manipulated_prior_dir = manipulated_prior_dir * (1. - C_delta_latents) # [batch, C_global_size]
    manipulated_prior_dir = tf.matmul(manipulated_prior_dir, prior_all_dirs) # [batch, prior_latent_size]
    prior_dir_to_go = prior_var_latents - manipulated_prior_dir
    prior_dir_to_go = autosummary('Loss/prior_dir_to_go', prior_dir_to_go)

    if latent_type == 'uniform':
        prior_latents = tf.random.uniform([minibatch_size, prior_latent_size], minval=-2, maxval=2)
    elif latent_type == 'normal':
        prior_latents = tf.random.normal([minibatch_size, prior_latent_size])
    elif latent_type == 'trunc_normal':
        prior_latents = tf.random.truncated_normal([minibatch_size, prior_latent_size])
    else:
        raise ValueError('Latent type not supported: ' + latent_type)

    prior_latents = autosummary('Loss/prior_latents', prior_latents)
    prior_delta_latents = prior_latents + prior_dir_to_go

    fake1_out = G.get_output_for(prior_latents, labels, is_training=True, randomize_noise=True, normalize_latents=False)
    fake2_out = G.get_output_for(prior_delta_latents, labels, is_training=True, randomize_noise=True, normalize_latents=False)
    fake1_out = autosummary('Loss/fake1_out', fake1_out)

    # regress_out_list = I.get_output_for(fake1_out, fake2_out, is_training=True)
    # regress_out = tf.concat(regress_out_list[:n_levels], axis=1)
    regress_out = I.get_output_for(fake1_out, fake2_out, is_training=True)

    # I_loss = calc_vc_loss(C_delta_latents[:,:sum(nd_out_list[:n_levels])], regress_out, C_global_size, D_lambda, C_lambda)
    I_loss = calc_vc_loss(C_delta_latents, regress_out, C_global_size, D_lambda, C_lambda)
    I_loss = autosummary('Loss/I_loss', I_loss)

    # dir_constraint = - tf.reduce_sum(prior_var_latents * prior_dir_to_go, axis=1)
    # dir_constraint = autosummary('Loss/dir_constraint', dir_constraint)
    dir_constraint = tf.reduce_sum(prior_var_latents * prior_dir_to_go, axis=1)
    norm_prior_var_latents = tf.math.sqrt(tf.reduce_sum(prior_var_latents * prior_var_latents, axis=1))
    norm_prior_dir_to_go = tf.math.sqrt(tf.reduce_sum(prior_dir_to_go * prior_dir_to_go, axis=1))
    dir_constraint = - dir_constraint / (norm_prior_var_latents * norm_prior_dir_to_go)
    dir_constraint = autosummary('Loss/dir_constraint', dir_constraint)

    I_loss = I_loss + hyperplane_lambda * hyperplane_constraint + hyperdir_lambda * dir_constraint

    return I_loss, None
