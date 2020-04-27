#!/usr/bin/python
#-*- coding: utf-8 -*-

# >.>.>.>.>.>.>.>.>.>.>.>.>.>.>.>.
# Licensed under the Apache License, Version 2.0 (the "License")
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0

# --- File Name: vc_modular_networks2.py
# --- Creation Date: 24-04-2020
# --- Last Modified: Mon 27 Apr 2020 03:42:47 AEST
# --- Author: Xinqi Zhu
# .<.<.<.<.<.<.<.<.<.<.<.<.<.<.<.<
"""
Modular networks for VC2
"""

import numpy as np
import tensorflow as tf
import dnnlib
import dnnlib.tflib as tflib
from dnnlib import EasyDict
from dnnlib.tflib.ops.upfirdn_2d import upsample_2d, downsample_2d
from dnnlib.tflib.ops.upfirdn_2d import upsample_conv_2d, conv_downsample_2d
from dnnlib.tflib.ops.fused_bias_act import fused_bias_act
from training.networks_stylegan2 import get_weight, dense_layer, conv2d_layer
from training.networks_stylegan2 import apply_bias_act, naive_upsample_2d
from training.networks_stylegan2 import naive_downsample_2d, modulated_conv2d_layer
from training.networks_stylegan2 import minibatch_stddev_layer
from stn.stn import spatial_transformer_network as transformer

LATENT_MODULES = [
    'D_global', 'C_nocond_global', 'C_global', 'SB', 'C_local_heat', 'C_local_hfeat'
]

#----------------------------------------------------------------------------
# Split module list from string
def split_module_names(module_list, **kwargs):
    '''
    Split the input module_list.
    e.g. ['Const-32', 'C_global-2', 'Conv-id-1',
            'Conv-up-1', 'SB-rotation-0', 'SB_scaling-2',
            'C_local_heat-2', 'Noise-1', 'C_local_hfeat-2',
            'SB_magnification-1', 'Conv-up-1', 'Noise-1', 'Conv-id-1',
            'SB-shearing-2', 'SB-translation-2', 'Conv-up-1',
            'C_local_heat-2', 'Conv-up-1', 'C_local_hfeat-1',
            'Noise-1', 'Conv-id-1']
    '''
    key_ls = []
    size_ls = []
    count_dlatent_size = 0
    # print('In split:', module_list)
    for module in module_list:
        m_name = module.split('-')[0]
        m_key = '-'.join(module.split('-')[:-1])  # exclude size
        size = int(module.split('-')[-1])
        if size > 0:
            if m_name in LATENT_MODULES:
                count_dlatent_size += size
            key_ls.append(m_key)
            size_ls.append(size)
    return key_ls, size_ls, count_dlatent_size

def torgb(x, y, num_channels):
    with tf.variable_scope('ToRGB'):
        t = apply_bias_act(conv2d_layer(x, fmaps=num_channels, kernel=1))
        return t if y is None else y + t

def build_Const_layers(init_dlatents_in, name, n_feats, scope_idx, dtype, **subkwargs):
    with tf.variable_scope(name + '-' + str(scope_idx)):
        x = tf.get_variable(
            'const',
            shape=[1, n_feats, 4, 4],
            initializer=tf.initializers.random_normal())
        x = tf.tile(tf.cast(x, dtype),
                    [tf.shape(init_dlatents_in)[0], 1, 1, 1])
    return x

def build_D_layers(x, name, n_latents, start_idx, scope_idx, dlatents_in,
                   act, fused_modconv, fmaps=128, **kwargs):
    '''
    Build discrete latent layers including label and D_global layers.
    '''
    with tf.variable_scope(name + '-' + str(scope_idx)):
        x = apply_bias_act(modulated_conv2d_layer(
            x,
            dlatents_in[:, start_idx:start_idx + n_latents],
            fmaps=fmaps,
            kernel=3,
            up=False,
            fused_modconv=fused_modconv),
                           act=act)
    return x


def build_C_global_layers(x, name, n_latents, start_idx, scope_idx, dlatents_in,
                          act, fused_modconv, fmaps=128, **kwargs):
    '''
    Build continuous latent layers, e.g. C_global layers.
    '''
    with tf.variable_scope(name + '-' + str(scope_idx)):
        C_global_latents = dlatents_in[:, start_idx:start_idx + n_latents]
        x = apply_bias_act(modulated_conv2d_layer(x, C_global_latents, fmaps=fmaps, kernel=3,
                                                  up=False, fused_modconv=fused_modconv), act=act)
    return x


def build_SB_layers(x, name, n_latents, start_idx, scope_idx, dlatents_in, n_content,
                    act, resample_kernel, fused_modconv, fmaps=128, **kwargs):
    '''
    Build spatial-biased networks modules.
    e.g. ['SB-rotation-0', 'SB_scaling-1', 'SB_magnification-1',
            'SB-shearing-2', 'SB-translation-2']
    '''
    sb_type = name.split('-')[-1]
    assert sb_type in [
        'rotation', 'scaling', 'magnification', 'shearing', 'translation'
    ]
    with tf.variable_scope(name + '-' + str(scope_idx)):
        if sb_type == 'magnification':
            assert n_latents == 1
            # [-2., 2.] --> [0.5, 1.]
            magnifier = (dlatents_in[:, start_idx:start_idx + n_latents]
                         + 6.) / 8.
            magnifier = tf.reshape(magnifier,
                                   [tf.shape(magnifier)[0], 1, 1, 1])
            x *= magnifier
        else:
            if sb_type == 'rotation':
                assert n_latents == 1
                theta = get_r_matrix(dlatents_in[:, start_idx:start_idx +
                                                       n_latents],
                                     dlatents_in[:, :n_content],
                                     act=act)
            elif sb_type == 'scaling':
                assert n_latents <= 2
                theta = get_s_matrix(dlatents_in[:, start_idx:start_idx +
                                                       n_latents],
                                     dlatents_in[:, :n_content],
                                     act=act)
            elif sb_type == 'shearing':
                assert n_latents <= 2
                theta = get_sh_matrix(
                    dlatents_in[:, start_idx:start_idx + n_latents],
                    dlatents_in[:, :n_content],
                    act=act)
            elif sb_type == 'translation':
                assert n_latents <= 2
                theta = get_t_matrix(dlatents_in[:, start_idx:start_idx +
                                                       n_latents],
                                     dlatents_in[:, :n_content],
                                     act=act)
            x = apply_st(x, theta)
    return x


def build_local_heat_layers(x, name, n_latents, start_idx, scope_idx,
                            dlatents_in, n_content, act, **kwargs):
    '''
    Build local heatmap layers. They control local strength by attention maps.
    '''
    with tf.variable_scope(name + '-' + str(scope_idx)):
        att_heat = get_att_heat(x, nheat=n_latents, act=act)
        # C_local_heat latent [-2, 2] --> [0, 1]
        heat_modifier = (
            2 + dlatents_in[:, start_idx:start_idx + n_latents]) / 4.
        heat_modifier = get_conditional_modifier(
            heat_modifier, dlatents_in[:, :n_content], act=act)
        heat_modifier = tf.reshape(
            heat_modifier, [tf.shape(heat_modifier)[0], n_latents, 1, 1])
        att_heat = att_heat * heat_modifier
        x = tf.concat([x, att_heat], axis=1)
    return x


def build_local_hfeat_layers(x, name, n_latents, start_idx, scope_idx,
                             dlatents_in, n_content, act, dtype, **kwargs):
    '''
    Build local heatmap*features.
    They contorl local presence of a feature by attention maps.
    '''
    with tf.variable_scope(name + '-' + str(scope_idx)):
        with tf.variable_scope('ConstFeats'):
            const_feats = tf.get_variable(
                'constfeats',
                shape=[1, n_latents, 32, 1, 1],
                initializer=tf.initializers.random_normal())
            const_feats = tf.tile(tf.cast(const_feats, dtype),
                                  [tf.shape(const_feats)[0], 1, 1, 1, 1])
        with tf.variable_scope('ControlAttHeat'):
            att_heat = get_att_heat(x, nheat=n_latents, act=act)
            att_heat = tf.reshape(att_heat,
                                  [tf.shape(att_heat)[0], n_latents, 1] +
                                  att_heat.shape.as_list()[2:4])
            # C_local_heat latent [-2, 2] --> [0, 1]
            hfeat_modifier = (
                2 + dlatents_in[:, start_idx:start_idx + n_latents]) / 4.
            hfeat_modifier = get_conditional_modifier(
                hfeat_modifier, dlatents_in[:, :n_content], act=act)
            hfeat_modifier = tf.reshape(hfeat_modifier,
                                        [tf.shape(x)[0], n_latents, 1, 1, 1])
            att_heat = att_heat * hfeat_modifier
            added_feats = const_feats * att_heat
            added_feats = tf.reshape(added_feats, [
                tf.shape(att_heat)[0], n_latents * att_heat.shape.as_list()[2]
            ] + att_heat.shape.as_list()[3:5])
            x = tf.concat([x, added_feats], axis=1)
    return x


def build_noise_layer(x, name, n_layers, scope_idx, act, use_noise, randomize_noise,
                      fmaps=128, **kwargs):
    for i in range(n_layers):
        with tf.variable_scope(name + '-' + str(scope_idx) + '-' + str(i)):
            x = conv2d_layer(x, fmaps=fmaps, kernel=3, up=False)
            if use_noise:
                if randomize_noise:
                    noise = tf.random_normal(
                        [tf.shape(x)[0], 1, x.shape[2], x.shape[3]],
                        dtype=x.dtype)
                else:
                    # noise = tf.get_variable(
                    # 'noise_variable-' + str(scope_idx) + '-' + str(i),
                    # shape=[1, 1, x.shape[2], x.shape[3]],
                    # initializer=tf.initializers.random_normal(),
                    # trainable=False)
                    noise_np = np.random.normal(size=(1, 1, x.shape[2],
                                                      x.shape[3]))
                    noise = tf.constant(noise_np)
                    noise = tf.cast(noise, x.dtype)
                noise_strength = tf.get_variable(
                    'noise_strength-' + str(scope_idx) + '-' + str(i),
                    shape=[],
                    initializer=tf.initializers.zeros())
                x += noise * tf.cast(noise_strength, x.dtype)
            x = apply_bias_act(x, act=act)
    return x


def build_conv_layer(x,
                     name,
                     n_layers,
                     scope_idx,
                     act,
                     resample_kernel,
                     fmaps=128,
                     **kwargs):
    # e.g. {'Conv-up': 2}, {'Conv-id': 1}
    sample_type = name.split('-')[-1]
    assert sample_type in ['up', 'down', 'id']
    for i in range(n_layers):
        with tf.variable_scope(name + '-' + str(scope_idx) + '-' + str(i)):
            x = apply_bias_act(conv2d_layer(x,
                                            fmaps=fmaps,
                                            kernel=3,
                                            up=(sample_type == 'up'),
                                            down=(sample_type == 'down'),
                                            resample_kernel=resample_kernel),
                               act=act)
    return x


def build_res_conv_layer(x, name, n_layers, scope_idx, act, resample_kernel, fmaps=128, **kwargs):
    # e.g. {'Conv-up': 2}, {'Conv-id': 1}
    sample_type = name.split('-')[-1]
    assert sample_type in ['up', 'down', 'id']
    x_ori = x
    for i in range(n_layers):
        with tf.variable_scope(name + '-' + str(scope_idx) + '-' + str(i)):
            x = apply_bias_act(conv2d_layer(x, fmaps=fmaps, kernel=3, up=(sample_type == 'up'),
                                            down=(sample_type == 'down'), resample_kernel=resample_kernel), act=act)
        if sample_type == 'up':
            with tf.variable_scope('Upsampling' + '-' + str(scope_idx) + '-' + str(i)):
                x_ori = naive_upsample_2d(x_ori)
        elif sample_type == 'down':
            with tf.variable_scope('Downsampling' + '-' + str(scope_idx) + '-' + str(i)):
                x_ori = naive_downsample_2d(x_ori)

    with tf.variable_scope(name + 'Resampled-' + str(scope_idx)):
        x_ori = apply_bias_act(conv2d_layer(x_ori, fmaps=fmaps, kernel=1), act=act)
        x = x + x_ori
    return x


# Return rotation matrix
def get_r_matrix(r_latents, cond_latent, act='lrelu'):
    # r_latents: [-2., 2.] -> [0, 2*pi]
    with tf.variable_scope('Condition0'):
        cond = apply_bias_act(dense_layer(cond_latent, fmaps=128), act=act)
    with tf.variable_scope('Condition1'):
        cond = apply_bias_act(dense_layer(cond, fmaps=1), act='sigmoid')
    rad = (r_latents + 2) / 4. * 2. * np.pi
    rad = rad * cond
    tt_00 = tf.math.cos(rad)
    tt_01 = -tf.math.sin(rad)
    tt_02 = tf.zeros_like(rad)
    tt_10 = tf.math.sin(rad)
    tt_11 = tf.math.cos(rad)
    tt_12 = tf.zeros_like(rad)
    theta = tf.concat([tt_00, tt_01, tt_02, tt_10, tt_11, tt_12], axis=1)
    return theta


# Return scaling matrix
def get_s_matrix(s_latents, cond_latent, act='lrelu'):
    # s_latents[:, 0]: [-2., 2.] -> [1., 3.]
    # s_latents[:, 1]: [-2., 2.] -> [1., 3.]
    if s_latents.shape.as_list()[1] == 1:
        with tf.variable_scope('Condition0'):
            cond = apply_bias_act(dense_layer(cond_latent, fmaps=128), act=act)
        with tf.variable_scope('Condition1'):
            cond = apply_bias_act(dense_layer(cond, fmaps=1), act='sigmoid')
        scale = (s_latents + 2.) * cond + 1.
        tt_00 = scale
        tt_01 = tf.zeros_like(scale)
        tt_02 = tf.zeros_like(scale)
        tt_10 = tf.zeros_like(scale)
        tt_11 = scale
        tt_12 = tf.zeros_like(scale)
    else:
        with tf.variable_scope('Condition0x'):
            cond_x = apply_bias_act(dense_layer(cond_latent, fmaps=128),
                                    act=act)
        with tf.variable_scope('Condition1x'):
            cond_x = apply_bias_act(dense_layer(cond_x, fmaps=1),
                                    act='sigmoid')
        with tf.variable_scope('Condition0y'):
            cond_y = apply_bias_act(dense_layer(cond_latent, fmaps=128),
                                    act=act)
        with tf.variable_scope('Condition1y'):
            cond_y = apply_bias_act(dense_layer(cond_y, fmaps=1),
                                    act='sigmoid')
        cond = tf.concat([cond_x, cond_y], axis=1)
        scale = (s_latents + 2.) * cond + 1.
        tt_00 = scale[:, 0:1]
        tt_01 = tf.zeros_like(scale[:, 0:1])
        tt_02 = tf.zeros_like(scale[:, 0:1])
        tt_10 = tf.zeros_like(scale[:, 1:])
        tt_11 = scale[:, 1:]
        tt_12 = tf.zeros_like(scale[:, 1:])
    theta = tf.concat([tt_00, tt_01, tt_02, tt_10, tt_11, tt_12], axis=1)
    return theta


# Return shear matrix
def get_sh_matrix(sh_latents, cond_latent, act='lrelu'):
    # sh_latents[:, 0]: [-2., 2.] -> [-1., 1.]
    # sh_latents[:, 1]: [-2., 2.] -> [-1., 1.]
    with tf.variable_scope('Condition0x'):
        cond_x = apply_bias_act(dense_layer(cond_latent, fmaps=128), act=act)
    with tf.variable_scope('Condition1x'):
        cond_x = apply_bias_act(dense_layer(cond_x, fmaps=1), act='sigmoid')
    with tf.variable_scope('Condition0y'):
        cond_y = apply_bias_act(dense_layer(cond_latent, fmaps=128), act=act)
    with tf.variable_scope('Condition1y'):
        cond_y = apply_bias_act(dense_layer(cond_y, fmaps=1), act='sigmoid')
    cond = tf.concat([cond_x, cond_y], axis=1)
    xy_shear = sh_latents / 2. * cond
    tt_00 = tf.ones_like(xy_shear[:, 0:1])
    tt_01 = xy_shear[:, 0:1]
    tt_02 = tf.zeros_like(xy_shear[:, 0:1])
    tt_10 = xy_shear[:, 1:]
    tt_11 = tf.ones_like(xy_shear[:, 1:])
    tt_12 = tf.zeros_like(xy_shear[:, 1:])
    theta = tf.concat([tt_00, tt_01, tt_02, tt_10, tt_11, tt_12], axis=1)
    return theta


# Return translation matrix
def get_t_matrix(t_latents, cond_latent, act='lrelu'):
    # t_latents[:, 0]: [-2., 2.] -> [-0.5, 0.5]
    # t_latents[:, 1]: [-2., 2.] -> [-0.5, 0.5]
    if t_latents.shape.as_list()[1] == 1:
        with tf.variable_scope('Condition0x'):
            cond = apply_bias_act(dense_layer(cond_latent, fmaps=128), act=act)
        with tf.variable_scope('Condition1x'):
            cond = apply_bias_act(dense_layer(cond, fmaps=1), act='sigmoid')
        xy_shift = t_latents / 4. * cond
        tt_00 = tf.ones_like(xy_shift)
        tt_01 = tf.zeros_like(xy_shift)
        tt_02 = xy_shift
        tt_10 = tf.zeros_like(xy_shift)
        tt_11 = tf.ones_like(xy_shift)
        tt_12 = xy_shift
    else:
        with tf.variable_scope('Condition0x'):
            cond_x = apply_bias_act(dense_layer(cond_latent, fmaps=128),
                                    act=act)
        with tf.variable_scope('Condition1x'):
            cond_x = apply_bias_act(dense_layer(cond_x, fmaps=1),
                                    act='sigmoid')
        with tf.variable_scope('Condition0y'):
            cond_y = apply_bias_act(dense_layer(cond_latent, fmaps=128),
                                    act=act)
        with tf.variable_scope('Condition1y'):
            cond_y = apply_bias_act(dense_layer(cond_y, fmaps=1),
                                    act='sigmoid')
        cond = tf.concat([cond_x, cond_y], axis=1)
        xy_shift = t_latents / 4. * cond
        tt_00 = tf.ones_like(xy_shift[:, 0:1])
        tt_01 = tf.zeros_like(xy_shift[:, 0:1])
        tt_02 = xy_shift[:, 0:1]
        tt_10 = tf.zeros_like(xy_shift[:, 1:])
        tt_11 = tf.ones_like(xy_shift[:, 1:])
        tt_12 = xy_shift[:, 1:]
    theta = tf.concat([tt_00, tt_01, tt_02, tt_10, tt_11, tt_12], axis=1)
    return theta


def apply_st(x, st_matrix):
    with tf.variable_scope('Transform'):
        x = tf.transpose(x, [0, 2, 3, 1])  # NCHW -> NHWC
        x = transformer(x, st_matrix, out_dims=x.shape.as_list()[1:3])
        x = tf.transpose(x, [0, 3, 1, 2])  # NHWC -> NCHW
    return x


def get_att_heat(x, nheat, act):
    with tf.variable_scope('Conv'):
        x = apply_bias_act(conv2d_layer(x, fmaps=128, kernel=3), act=act)
    with tf.variable_scope('ConvAtt'):
        x = apply_bias_act(conv2d_layer(x, fmaps=1, kernel=3), act='sigmoid')
    return x


def get_conditional_modifier(modifier, cond_latent, act='lrelu'):
    with tf.variable_scope('Condition0'):
        cond = apply_bias_act(dense_layer(cond_latent, fmaps=128), act=act)
    with tf.variable_scope('Condition1'):
        cond = apply_bias_act(dense_layer(cond,
                                          fmaps=modifier.shape.as_list()[1]),
                              act='sigmoid')
    modifier = modifier * cond
    return modifier