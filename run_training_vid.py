#!/usr/bin/python
#-*- coding: utf-8 -*-

# >.>.>.>.>.>.>.>.>.>.>.>.>.>.>.>.
# Licensed under the Apache License, Version 2.0 (the "License")
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0

# --- File Name: run_training_vid.py
# --- Creation Date: 23-03-2020
# --- Last Modified: Wed 01 Apr 2020 22:20:10 AEDT
# --- Author: Xinqi Zhu
# .<.<.<.<.<.<.<.<.<.<.<.<.<.<.<.<
"""
Run training file for vid_model related networks use.
Code borrowed from run_training.py from NVIDIA.
"""

import argparse
import copy
import os
import sys

import dnnlib
from dnnlib import EasyDict

from metrics.metric_defaults import metric_defaults
from training.spatial_biased_modular_networks import split_module_names, LATENT_MODULES

#----------------------------------------------------------------------------

_valid_configs = [
    # Table 1
    'config-e',  # + No growing, new G & D arch.
    'config-f',  # + Large networks (default)
]

#----------------------------------------------------------------------------


def run(dataset, data_dir, result_dir, config_id, num_gpus, total_kimg, gamma,
        mirror_augment, metrics, resume_pkl, fmap_decay=0.15, D_lambda=1,
        C_lambda=1, MI_lambda=1, cls_alpha=0, n_samples_per=10, module_list=None,
        single_const=True, model_type='spatial_biased', phi_blurry=0.5,
        latent_type='uniform'):

    train = EasyDict(run_func_name='training.training_loop_vid.training_loop_vid'
                     )  # Options for training loop.

    D_global_size = 0

    module_list = _str_to_list(module_list)
    key_ls, size_ls, count_dlatent_size, _ = split_module_names(
        module_list)
    for i, key in enumerate(key_ls):
        if key.startswith('D_global'):
            D_global_size += size_ls[i]
            break
    print('D_global_size:', D_global_size)
    print('key_ls:', key_ls)
    print('size_ls:', size_ls)
    print('count_dlatent_size:', count_dlatent_size)

    if model_type == 'vid_model':
        G = EasyDict(
            func_name='training.vid_networks.G_main_vid',
            synthesis_func='G_synthesis_vid_modular',
            fmap_min=16, fmap_max=512, fmap_decay=fmap_decay, latent_size=count_dlatent_size,
            dlatent_size=count_dlatent_size, D_global_size=D_global_size,
            module_list=module_list, single_const=single_const,
            use_noise=True)  # Options for generator network.
        I = EasyDict(func_name='training.vid_networks.vid_head',
            dlatent_size=count_dlatent_size, D_global_size=D_global_size, fmap_max=512)
        D = EasyDict(func_name='training.networks_stylegan2.D_stylegan2',
            fmap_max=512)  # Options for discriminator network.
        I_info = EasyDict()
        desc = model_type
    elif model_type == 'vid_with_cls':
        G = EasyDict(
            func_name='training.vid_networks.G_main_vid',
            synthesis_func='G_synthesis_vid_modular',
            fmap_min=16, fmap_max=512, fmap_decay=fmap_decay, latent_size=count_dlatent_size,
            dlatent_size=count_dlatent_size, D_global_size=D_global_size,
            module_list=module_list, single_const=single_const,
            use_noise=True)  # Options for generator network.
        I = EasyDict(func_name='training.vid_networks.vid_head',
            dlatent_size=count_dlatent_size, D_global_size=D_global_size, fmap_max=512)
        I_info = EasyDict(func_name='training.info_gan_networks.info_gan_head_cls',
                     dlatent_size=count_dlatent_size, D_global_size=D_global_size,
                     fmap_decay=fmap_decay, fmap_min=16, fmap_max=512)
        D = EasyDict(
            func_name='training.info_gan_networks.D_info_gan_stylegan2',
            fmap_max=512)  # Options for discriminator network.
        desc = model_type
    elif model_type == 'vid_naive_cluster_model':
        G = EasyDict(
            func_name='training.vid_networks.G_main_vid',
            synthesis_func='G_synthesis_vid_modular',
            fmap_min=16, fmap_max=512, fmap_decay=fmap_decay, latent_size=count_dlatent_size,
            dlatent_size=count_dlatent_size, D_global_size=D_global_size,
            module_list=module_list, single_const=single_const,
            use_noise=True)  # Options for generator network.
        I = EasyDict(func_name='training.vid_networks.vid_naive_cluster_head',
            dlatent_size=count_dlatent_size, D_global_size=D_global_size,
                     fmap_max=512)  # Options for estimator network.
        D = EasyDict(func_name='training.networks_stylegan2.D_stylegan2',
            fmap_max=512)  # Options for discriminator network.
        I_info = EasyDict()
        desc = model_type
    elif model_type == 'vid_blurry_model':
        G = EasyDict(
            func_name='training.vid_networks.G_main_vid',
            synthesis_func='G_synthesis_vid_modular',
            fmap_min=16, fmap_max=512, fmap_decay=fmap_decay, latent_size=count_dlatent_size,
            dlatent_size=count_dlatent_size, D_global_size=D_global_size,
            module_list=module_list, single_const=single_const,
            use_noise=True)  # Options for generator network.
        I = EasyDict(func_name='training.vid_networks.vid_naive_cluster_head',
            dlatent_size=count_dlatent_size, D_global_size=D_global_size,
                     fmap_max=512)  # Options for estimator network.
        D = EasyDict(func_name='training.networks_stylegan2.D_stylegan2',
            fmap_max=512)  # Options for discriminator network.
        I_info = EasyDict()
        desc = model_type
    else:
        raise ValueError('Not supported model tyle: ' + model_type)


    G_opt = EasyDict(beta1=0.0, beta2=0.99,
                     epsilon=1e-8)  # Options for generator optimizer.
    D_opt = EasyDict(beta1=0.0, beta2=0.99,
                     epsilon=1e-8)  # Options for discriminator optimizer.
    I_opt = EasyDict(beta1=0.0, beta2=0.99,
                     epsilon=1e-8)  # Options for discriminator optimizer.
    if model_type == 'vid_model':
        G_loss = EasyDict(func_name='training.loss_vid.G_logistic_ns_vid',
            D_global_size=D_global_size, C_lambda=C_lambda,
            latent_type=latent_type)  # Options for generator loss.
        D_loss = EasyDict(func_name='training.loss_vid.D_logistic_r1_vid',
            D_global_size=D_global_size, latent_type=latent_type)  # Options for discriminator loss.
        I_loss = EasyDict(func_name='training.loss_vid.I_vid',
            D_global_size=D_global_size, latent_type=latent_type,
                          C_lambda=C_lambda, MI_lambda=MI_lambda)  # Options for estimator loss.
    elif model_type == 'vid_with_cls':
        G_loss = EasyDict(func_name='training.loss_vid.G_logistic_ns_vid',
            D_global_size=D_global_size, C_lambda=C_lambda, cls_alpha=cls_alpha,
            latent_type=latent_type)  # Options for generator loss.
        D_loss = EasyDict(func_name='training.loss_vid.D_logistic_r1_info_gan_vid',
            D_global_size=D_global_size, latent_type=latent_type)  # Options for discriminator loss.
        I_loss = EasyDict(func_name='training.loss_vid.I_vid',
            D_global_size=D_global_size, latent_type=latent_type,
                          C_lambda=C_lambda, MI_lambda=MI_lambda)  # Options for estimator loss.
    elif model_type == 'vid_naive_cluster_model':
        G_loss = EasyDict(func_name='training.loss_vid.G_logistic_ns_vid_naive_cluster',
            D_global_size=D_global_size, C_lambda=C_lambda,
            latent_type=latent_type)  # Options for generator loss.
        D_loss = EasyDict(func_name='training.loss_vid.D_logistic_r1_vid',
            D_global_size=D_global_size, latent_type=latent_type)  # Options for discriminator loss.
        I_loss = EasyDict()  # Options for estimator loss.
        I_opt = EasyDict()
    elif model_type == 'vid_blurry_model':
        G_loss = EasyDict(func_name='training.loss_vid.G_logistic_ns_vid_naive_cluster',
            D_global_size=D_global_size, C_lambda=C_lambda,
            latent_type=latent_type)  # Options for generator loss.
        D_loss = EasyDict(func_name='training.loss_vid.D_logistic_r1_vid',
            D_global_size=D_global_size, latent_type=latent_type)  # Options for discriminator loss.
        I_loss = EasyDict(func_name='training.loss_vid.I_vid_blurry',
            D_global_size=D_global_size, latent_type=latent_type,
                          C_lambda=C_lambda, MI_lambda=MI_lambda, phi=phi_blurry)  # Options for estimator loss.
    else:
        raise ValueError('Not supported loss tyle: ' + model_type)

    sched = EasyDict()  # Options for TrainingSchedule.
    grid = EasyDict(size='1080p', layout='random')  # Options for setup_snapshot_image_grid().
    sc = dnnlib.SubmitConfig()  # Options for dnnlib.submit_run().
    tf_config = {'rnd.np_random_seed': 1000}  # Options for tflib.init_tf().

    train.data_dir = data_dir
    train.total_kimg = total_kimg
    train.mirror_augment = mirror_augment
    train.image_snapshot_ticks = train.network_snapshot_ticks = 10
    sched.G_lrate_base = sched.D_lrate_base = sched.I_lrate_base = 0.002
    sched.minibatch_size_base = 16
    sched.minibatch_gpu_base = 8
    D_loss.gamma = 10
    metrics = [metric_defaults[x] for x in metrics]

    desc += '-' + dataset
    dataset_args = EasyDict(tfrecord_dir=dataset, max_label_size='full')

    assert num_gpus in [1, 2, 4, 8]
    sc.num_gpus = num_gpus
    desc += '-%dgpu' % num_gpus

    assert config_id in _valid_configs
    desc += '-' + config_id

    # Configs A-E: Shrink networks to match original StyleGAN.
    if config_id != 'config-f':
        # I.fmap_base = G.fmap_base = D.fmap_base = 8 << 10
        I.fmap_base = G.fmap_base = D.fmap_base = 2 << 8

    # Config E: Set gamma to 100 and override G & D architecture.
    if config_id.startswith('config-e'):
        D_loss.gamma = 100
        if 'Gorig' in config_id: G.architecture = 'orig'
        if 'Gskip' in config_id: G.architecture = 'skip'  # (default)
        if 'Gresnet' in config_id: G.architecture = 'resnet'
        if 'Dorig' in config_id: D.architecture = 'orig'
        if 'Dskip' in config_id: D.architecture = 'skip'
        if 'Dresnet' in config_id: D.architecture = 'resnet'  # (default)

    if gamma is not None:
        D_loss.gamma = gamma

    sc.submit_target = dnnlib.SubmitTarget.LOCAL
    sc.local.do_not_copy_source_files = True
    kwargs = EasyDict(train)
    kwargs.update(G_args=G, D_args=D, I_args=I, I_info_args=I_info,
                  G_opt_args=G_opt, D_opt_args=D_opt, I_opt_args=I_opt,
                  G_loss_args=G_loss, D_loss_args=D_loss, I_loss_args=I_loss,
                  use_vid_head=(model_type == 'vid_model'),
                  use_vid_head_with_cls=(model_type == 'vid_with_cls'),
                  use_vid_naive_cluster=(model_type == 'vid_naive_cluster_model'),
                  use_vid_blurry=(model_type == 'vid_blurry_model'),
                  traversal_grid=True)
    n_continuous = 0
    for i, key in enumerate(key_ls):
        m_name = key.split('-')[0]
        if (m_name in LATENT_MODULES) and (not m_name == 'D_global'):
            n_continuous += size_ls[i]

    kwargs.update(dataset_args=dataset_args, sched_args=sched, grid_args=grid,
                  metric_arg_list=metrics, tf_config=tf_config,
                  resume_pkl=resume_pkl, n_discrete=D_global_size,
                  n_continuous=n_continuous, n_samples_per=n_samples_per,
                  C_lambda=C_lambda, MI_lambda=MI_lambda)
    kwargs.submit_config = copy.deepcopy(sc)
    kwargs.submit_config.run_dir_root = result_dir
    kwargs.submit_config.run_desc = desc
    dnnlib.submit_run(**kwargs)


#----------------------------------------------------------------------------


def _str_to_bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')


def _str_to_list(v):
    v_values = v.strip()[1:-1]
    module_list = [x.strip() for x in v_values.split(',')]
    return module_list


def _parse_comma_sep(s):
    if s is None or s.lower() == 'none' or s == '':
        return []
    return s.split(',')


#----------------------------------------------------------------------------

_examples = '''examples:
  # Train vid net using the celeba dataset
  CUDA_VISIBLE_DEVICES=1 python %(prog)s --num-gpus=1 \
  --data-dir=/mnt/hdd/Datasets/CelebA_dataset --dataset=celeba_tfr
'''


def main():
    parser = argparse.ArgumentParser(
        description='Train VID Models.',
        epilog=_examples,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        '--result-dir',
        help='Root directory for run results (default: %(default)s)',
        default='results',
        metavar='DIR')
    parser.add_argument('--data-dir', help='Dataset root directory', required=True)
    parser.add_argument('--dataset', help='Training dataset', required=True)
    parser.add_argument('--config', help='Training config (default: %(default)s)',
                        default='config-e', dest='config_id', metavar='CONFIG')
    parser.add_argument('--num-gpus', help='Number of GPUs (default: %(default)s)',
                        default=1, type=int, metavar='N')
    parser.add_argument('--total-kimg',
        help='Training length in thousands of images (default: %(default)s)',
        metavar='KIMG', default=25000, type=int)
    parser.add_argument('--gamma',
        help='R1 regularization weight (default is config dependent)',
        default=None, type=float)
    parser.add_argument('--mirror-augment', help='Mirror augment (default: %(default)s)',
                        default=False, metavar='BOOL', type=_str_to_bool)
    parser.add_argument(
        '--metrics', help='Comma-separated list of metrics or "none" (default: %(default)s)',
        default='None', type=_parse_comma_sep)
    parser.add_argument('--model_type', help='Type of model to train', default='vid_model',
                        type=str, metavar='MODEL_TYPE', choices=['info_gan', 'vid_model', 
                                                                 'vid_with_cls', 'vid_naive_cluster_model', 
                                                                 'vid_blurry_model'])
    parser.add_argument('--resume_pkl', help='Continue training using pretrained pkl.',
                        default=None, metavar='RESUME_PKL', type=str)
    parser.add_argument('--n_samples_per', help='Number of samples for each line in traversal (default: %(default)s)',
        metavar='N_SHOWN_SAMPLES_PER_LINE', default=10, type=int)
    parser.add_argument('--module_list', help='Module list for modular network.',
                        default=None, metavar='MODULE_LIST', type=str)
    parser.add_argument(
        '--single_const',
        help='Use a single constant feature at the top or not (if not, n_classes of const feature maps will be used and gathered).',
        default=True, metavar='BOOL', type=_str_to_bool)
    parser.add_argument('--D_lambda', help='Discrete lambda.',
                        metavar='D_LAMBDA', default=1, type=float)
    parser.add_argument('--C_lambda', help='Continuous lambda.',
                        metavar='C_LAMBDA', default=1, type=float)
    parser.add_argument('--MI_lambda', help='MINE lambda.',
                        metavar='MI_LAMBDA', default=1, type=float)
    parser.add_argument('--cls_alpha', help='Classification hyper.',
                        metavar='CLS_ALPHA', default=0, type=float)
    parser.add_argument('--latent_type', help='What type of latent priori to use.',
                        metavar='LATENT_TYPE', default='uniform', choices=['uniform', 'normal', 'trunc_normal'], type=str)
    parser.add_argument('--fmap_decay', help='fmap decay for network building.',
                        metavar='FMAP_DECAY', default=0.15, type=float)
    parser.add_argument('--phi_blurry', help='Phi in blurry loss.',
                        metavar='PHI_BLURRY', default=0.5, type=float)

    args = parser.parse_args()

    if not os.path.exists(args.data_dir):
        print('Error: dataset root directory does not exist.')
        sys.exit(1)

    if args.config_id not in _valid_configs:
        print('Error: --config value must be one of: ',
              ', '.join(_valid_configs))
        sys.exit(1)

    for metric in args.metrics:
        if metric not in metric_defaults:
            print('Error: unknown metric \'%s\'' % metric)
            sys.exit(1)

    run(**vars(args))


#----------------------------------------------------------------------------

if __name__ == "__main__":
    main()

#----------------------------------------------------------------------------
