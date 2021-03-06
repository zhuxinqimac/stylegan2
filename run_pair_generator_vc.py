#!/usr/bin/python
#-*- coding: utf-8 -*-

# >.>.>.>.>.>.>.>.>.>.>.>.>.>.>.>.
# Licensed under the Apache License, Version 2.0 (the "License")
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0

# --- File Name: run_pair_generator_vc.py
# --- Creation Date: 27-02-2020
# --- Last Modified: Mon 09 Nov 2020 00:06:38 AEDT
# --- Author: Xinqi Zhu
# .<.<.<.<.<.<.<.<.<.<.<.<.<.<.<.<
"""
Generate a image-pair dataset
"""

import argparse
import numpy as np
from PIL import Image
import dnnlib
import dnnlib.tflib as tflib
import re
import os
import sys
import pdb

import pretrained_networks
from training import misc
from training.utils import get_return_v
from training.training_loop_dsp import get_grid_latents

#----------------------------------------------------------------------------


def generate_image_pairs(network_pkl,
                         n_imgs,
                         model_type,
                         n_discrete,
                         n_continuous,
                         result_dir,
                         batch_size=10,
                         return_atts=True,
                         latent_type='onedim',
                         act_mask_ls=None):
    print('Loading networks from "%s"...' % network_pkl)
    tflib.init_tf()
    if (model_type == 'info_gan') or (model_type == 'vc_gan_with_vc_head'):
        _G, _D, I, Gs = misc.load_pkl(network_pkl)
    else:
        _G, _D, Gs = misc.load_pkl(network_pkl)

    if not os.path.exists(result_dir):
        os.makedirs(result_dir)

    # _G, _D, Gs = pretrained_networks.load_networks(network_pkl)

    Gs_kwargs = dnnlib.EasyDict()
    Gs_kwargs.randomize_noise = False
    Gs_kwargs.return_atts = return_atts

    n_batches = n_imgs // batch_size

    if act_mask_ls is None:
        act_mask_ls = np.arange(n_continuous)
    n_act = len(act_mask_ls) # e.g. act_mask_ls: [0,2,3,5]
    act_mask_dup_array = np.tile(np.array(act_mask_ls)[np.newaxis, ...], [batch_size, 1])
    for i in range(n_batches):
        print('Generating image pairs %d/%d ...' % (i, n_batches))
        grid_labels = np.zeros([batch_size, 0], dtype=np.float32)

        if n_discrete > 0:
            cat_dim = np.random.randint(0, n_discrete, size=[batch_size])
            cat_onehot = np.zeros((batch_size, n_discrete))
            cat_onehot[np.arange(cat_dim.size), cat_dim] = 1

        # z_1 = np.random.normal(size=[batch_size, n_continuous])
        # z_2 = np.random.normal(size=[batch_size, n_continuous])
        # if latent_type == 'onedim':
            # delta_dim = np.random.randint(0, n_continuous, size=[batch_size])
            # delta_onehot = np.zeros((batch_size, n_continuous))
            # delta_onehot[np.arange(delta_dim.size), delta_dim] = 1
            # z_2 = np.where(delta_onehot > 0, z_2, z_1)


        # New
        z_1 = np.random.normal(size=[batch_size, n_continuous])
        z_2 = np.random.normal(size=[batch_size, n_continuous])
        if latent_type == 'onedim':
            delta_dim_act = np.random.randint(0, n_act, size=[batch_size])
            delta_dim = act_mask_dup_array[np.arange(batch_size), delta_dim_act]
            delta_onehot = np.zeros((batch_size, n_continuous))
            delta_onehot[np.arange(delta_dim.size), delta_dim] = 1
            z_2 = np.where(delta_onehot > 0, z_2, z_1)
        # print('z1:', z_1)
        # print('z2:', z_2)
        # pdb.set_trace()

        delta_z = z_1 - z_2

        if i == 0:
            labels = delta_z
        else:
            labels = np.concatenate([labels, delta_z], axis=0)

        if n_discrete > 0:
            z_1 = np.concatenate((cat_onehot, z_1), axis=1)
            z_2 = np.concatenate((cat_onehot, z_2), axis=1)

        fakes_1 = get_return_v(
            Gs.run(z_1,
                   grid_labels,
                   is_validation=True,
                   minibatch_size=batch_size,
                   **Gs_kwargs), 1)
        fakes_2 = get_return_v(
            Gs.run(z_2,
                   grid_labels,
                   is_validation=True,
                   minibatch_size=batch_size,
                   **Gs_kwargs), 1)
        print('fakes_1.shape:', fakes_1.shape)
        print('fakes_2.shape:', fakes_2.shape)

        for j in range(fakes_1.shape[0]):
            pair_np = np.concatenate([fakes_1[j], fakes_2[j]], axis=2)
            img = misc.convert_to_pil_image(pair_np, [-1, 1])
            # pair_np = (pair_np * 255).astype(np.uint8)
            # img = Image.fromarray(pair_np)
            img.save(
                os.path.join(result_dir,
                             'pair_%06d.jpg' % (i * batch_size + j)))
    np.save(os.path.join(result_dir, 'labels.npy'), labels)


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

def _str_to_list_of_int(v):
    v_values = v.strip()[1:-1]
    step_list = [int(x.strip()) for x in v_values.split(',')]
    return step_list


_examples = '''examples:

  # Generate image pairs
  python %(prog)s --network_pkl=results/info_gan.pkl --n_imgs=5 --result_dir ./results
'''


#----------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description='VC-GAN and INFO-GAN image-pair generator.',
        epilog=_examples,
        formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('--network_pkl',
                        help='Network pickle filename',
                        required=True)
    parser.add_argument('--n_imgs',
                        type=int,
                        help='Number of image pairs to generate',
                        required=True)
    parser.add_argument('--n_discrete',
                        type=int,
                        help='Number of discrete latents',
                        default=0)
    parser.add_argument('--n_continuous',
                        type=int,
                        help='Number of continuous latents',
                        default=14)
    parser.add_argument('--batch_size',
                        type=int,
                        help='Batch size for generation',
                        default=10)
    parser.add_argument('--latent_type',
                        type=str,
                        help='What type of latent difference to use',
                        default='onedim',
                        choices=['onedim', 'fulldim'])
    parser.add_argument('--model_type',
                        type=str,
                        help='Which model is this pkl',
                        default='vc_gan_with_vc_head',
                        choices=['info_gan', 'vc_gan', 'vc_gan_with_vc_head'])
    parser.add_argument('--result-dir',
                        help='Root directory to store this dataset',
                        required=True,
                        metavar='DIR')
    parser.add_argument('--return_atts',
                        help='If return atts.',
                        default=False,
                        metavar='RETURN_ATTS',
                        type=_str_to_bool)
    parser.add_argument('--act_mask_ls',
                        help='The list of active latent dimensions.',
                        default=None,
                        metavar='ACT_MASK_LS',
                        type=_str_to_list_of_int)

    args = parser.parse_args()
    kwargs = vars(args)

    sc = dnnlib.SubmitConfig()
    sc.num_gpus = 1
    sc.submit_target = dnnlib.SubmitTarget.LOCAL
    sc.local.do_not_copy_source_files = True
    sc.run_dir_root = kwargs['result_dir']

    dnnlib.submit_run(sc, 'run_pair_generator_vc.generate_image_pairs',
                      **kwargs)


#----------------------------------------------------------------------------

if __name__ == "__main__":
    main()

#----------------------------------------------------------------------------
