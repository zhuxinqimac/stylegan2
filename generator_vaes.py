#!/usr/bin/python
#-*- coding: utf-8 -*-

# >.>.>.>.>.>.>.>.>.>.>.>.>.>.>.>.
# Licensed under the Apache License, Version 2.0 (the "License")
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0

# --- File Name: generator_vaes.py
# --- Creation Date: 05-10-2020
# --- Last Modified: Mon 05 Oct 2020 19:12:09 AEDT
# --- Author: Xinqi Zhu
# .<.<.<.<.<.<.<.<.<.<.<.<.<.<.<.<
"""
Generate script of vae networks.
"""

import argparse
import numpy as np
import PIL.Image
import dnnlib
import dnnlib.tflib as tflib
import re
import pdb
import sys
import os
import collections
import cv2

import pretrained_networks
from training import misc
from training.utils import add_outline, get_return_v

def create_rot_mat(rot):
    theta = np.radians(rot)
    c, s = np.cos(theta), np.sin(theta)
    R = np.array(((c, -s), (s, c)))
    return R

def sample_grid_z(rnd, G, latent_pair, n_samples_per, bound, rot):
    z = rnd.randn(1, *G.input_shape[1:])
    z = np.tile(z, (n_samples_per*n_samples_per, 1))
    xs = np.linspace(-bound, bound, n_samples_per)
    ys = np.linspace(-bound, bound, n_samples_per)
    xv, yv = np.meshgrid(xs, ys) # [n_samples, n_samples], [n_samples, n_samples]
    xv = np.reshape(xv, (-1, 1))
    yv = np.reshape(yv, (-1, 1))
    points = np.concatenate((xv, yv), axis=1) # [n_samples*n_samples, 2]
    rot_mat = create_rot_mat(rot) # [2, 2]
    points_transed = np.dot(points, rot_mat) # [n_samples*n_samples, 2]
    for i, lat_i in enumerate(latent_pair):
        z[:, lat_i] = points_transed[:, i]
    return z

def measure_distance(images, n_samples_per):
    assert images.shape[0] == n_samples_per * n_samples_per
    distance_measure = misc.load_pkl('http://d36zk2xti64re0.cloudfront.net/stylegan1/networks/metrics/vgg16_zhang_perceptual.pkl')
    dis_sum = 0
    for i in range(n_samples_per):
        v = get_return_v(distance_measure.run(images[i*n_samples_per: (i+1)*n_samples_per-1],
                                              images[i*n_samples_per+1: (i+1)*n_samples_per]), 1)
        dis_sum += v.sum()
    return dis_sum

def generate_grids(network, seeds, latent_pair, n_samples_per=10, bound=2, rot=0):
    tflib.init_tf()
    print('Loading networks from "%s"...' % network)
    E, G = get_return_v(misc.load_pkl(network), 2)

    G_kwargs = dnnlib.EasyDict()
    G_kwargs.is_validation = True
    G_kwargs.randomize_noise = True

    distance_ls = []
    for seed_idx, seed in enumerate(seeds):
        print('Generating images for seed %d (%d/%d) ...' % (seed, seed_idx, len(seeds)))
        rnd = np.random.RandomState(seed)
        z = sample_grid_z(rnd, G, latent_pair, n_samples_per, bound, rot)
        images = get_return_v(G.run(z, None, **G_kwargs), 1) # [n_samples_per*n_samples_per, channel, height, width]

        distance_ls.append(measure_distance(images, n_samples_per))

        images = add_outline(images, width=1)
        n_samples_square, c, h, w = np.shape(images)
        assert n_samples_square == n_samples_per * n_samples_per
        images = np.reshape(images, (n_samples_per, n_samples_per, c, h, w))
        images = np.transpose(images, [0, 3, 1, 4, 2])
        images = np.reshape(images, (n_samples_per*h, n_samples_per*w, c))
        images = misc.adjust_dynamic_range(images, [0, 1], [0, 255])
        images = np.rint(images).clip(0, 255).astype(np.uint8)
        PIL.Image.fromarray(images, 'RGB').save(dnnlib.make_run_dir_path('seed%04d.png' % seed))
    print('mean_distance:', np.mean(np.array(distance_ls)))

def _parse_num_range(s):
    '''Accept either a comma separated list of numbers 'a,b,c' or a range 'a-c' and return as a list of ints.'''

    range_re = re.compile(r'^(\d+)-(\d+)$')
    m = range_re.match(s)
    if m:
        return range(int(m.group(1)), int(m.group(2))+1)
    vals = s.split(',')
    return [int(x) for x in vals]

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
    module_list = [int(x.strip()) for x in v.split('_')]
    return module_list

#----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="VAE generators."
    )

    subparsers = parser.add_subparsers(help='Sub-commands', dest='command')

    parser_generate_images = subparsers.add_parser('generate-grids', help='Generate grids')
    parser_generate_images.add_argument('--network', help='Network pickle filename', required=True)
    parser_generate_images.add_argument('--seeds', type=_parse_num_range, help='List of random seeds', required=True)
    parser_generate_images.add_argument('--latent_pair', type=_str_to_list_of_int, help='latent pair index', default='0_1')
    parser_generate_images.add_argument('--n_samples_per', type=int, help='number of samples per row in grid', default=10)
    parser_generate_images.add_argument('--bound', type=float, help='interval [-bound, bound] for traversal', default=2)
    parser_generate_images.add_argument('--rot', type=float, help='rotation degree of traversal coordinate system', default=0)
    parser_generate_images.add_argument('--result-dir', help='Root directory for run results (default: %(default)s)', default='results', metavar='DIR')

    args = parser.parse_args()
    kwargs = vars(args)
    subcmd = kwargs.pop('command')

    if subcmd is None:
        print ('Error: missing subcommand.  Re-run with --help for usage.')
        sys.exit(1)

    sc = dnnlib.SubmitConfig()
    sc.num_gpus = 1
    sc.submit_target = dnnlib.SubmitTarget.LOCAL
    sc.local.do_not_copy_source_files = True
    sc.run_dir_root = kwargs.pop('result_dir')
    sc.run_desc = subcmd

    func_name_map = {
        'generate-grids': 'generator_vaes.generate_grids',
    }
    dnnlib.submit_run(sc, func_name_map[subcmd], **kwargs)

#----------------------------------------------------------------------------

if __name__ == "__main__":
    main()

#----------------------------------------------------------------------------