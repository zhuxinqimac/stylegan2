# Copyright (c) 2019, NVIDIA Corporation. All rights reserved.
#
# This work is made available under the Nvidia Source Code License-NC.
# To view a copy of this license, visit
# https://nvlabs.github.io/stylegan2/license.html

"""Default metric definitions."""

from dnnlib import EasyDict

#----------------------------------------------------------------------------

metric_defaults = EasyDict([(args.name, args) for args in [
    EasyDict(name='fid50k',    func_name='metrics.frechet_inception_distance.FID', num_images=50000, minibatch_per_gpu=8),
    EasyDict(name='is50k',     func_name='metrics.inception_score.IS',             num_images=50000, num_splits=10, minibatch_per_gpu=8),
    EasyDict(name='ppl_zfull', func_name='metrics.perceptual_path_length.PPL',     num_samples=50000, epsilon=1e-4, space='z', sampling='full', crop=True, minibatch_per_gpu=4, Gs_overrides=dict(dtype='float32', mapping_dtype='float32')),
    EasyDict(name='ppl_wfull', func_name='metrics.perceptual_path_length.PPL',     num_samples=50000, epsilon=1e-4, space='w', sampling='full', crop=True, minibatch_per_gpu=4, Gs_overrides=dict(dtype='float32', mapping_dtype='float32')),
    EasyDict(name='ppl_zend',  func_name='metrics.perceptual_path_length.PPL',     num_samples=50000, epsilon=1e-4, space='z', sampling='end', crop=True, minibatch_per_gpu=4, Gs_overrides=dict(dtype='float32', mapping_dtype='float32')),
    EasyDict(name='ppl_wend',  func_name='metrics.perceptual_path_length.PPL',     num_samples=50000, epsilon=1e-4, space='w', sampling='end', crop=True, minibatch_per_gpu=4, Gs_overrides=dict(dtype='float32', mapping_dtype='float32')),
    EasyDict(name='ppl2_wend', func_name='metrics.perceptual_path_length.PPL',     num_samples=50000, epsilon=1e-4, space='w', sampling='end', crop=False, minibatch_per_gpu=4, Gs_overrides=dict(dtype='float32', mapping_dtype='float32')),
    EasyDict(name='ls',        func_name='metrics.linear_separability.LS',         num_samples=200000, num_keep=100000, attrib_indices=range(40), minibatch_per_gpu=4),
    EasyDict(name='pr50k3',    func_name='metrics.precision_recall.PR',            num_images=50000, nhood_size=3, minibatch_per_gpu=8, row_batch_size=10000, col_batch_size=10000),
    EasyDict(name='tpl',  func_name='metrics.traversal_perceptual_length.TPL',     n_samples_per_dim=25, crop=False, n_traversals=50, no_mapping=False, Gs_overrides=dict(dtype='float32', mapping_dtype='float32')),
    EasyDict(name='tpl_nomap',  func_name='metrics.traversal_perceptual_length.TPL',     n_samples_per_dim=25, crop=False, n_traversals=50, no_mapping=True, active_thresh=0, Gs_overrides=dict(dtype='float32', mapping_dtype='float32')),
    EasyDict(name='factorvae_dsprites_all',  func_name='metrics.factor_vae_metric.FactorVAEMetric',     dataset_dir='/mnt/hdd/Datasets/dsprites/dsprites_all_noshuffle_tfr', dataset_name='Dsprites', use_latents='[0,1,2,3,4]', batch_size=60, num_train=10000, num_eval=5000, num_variance_estimate=10000),
    EasyDict(name='factorvae_dsprites_all_hpc',  func_name='metrics.factor_vae_metric.FactorVAEMetric',     dataset_dir='/project/xqzhu/disentangle_datasets/dsprites/dsprites_all_noshuffle_tfr', dataset_name='Dsprites', use_latents='[0,1,2,3,4]', batch_size=60, num_train=10000, num_eval=5000, num_variance_estimate=10000),
    EasyDict(name='factorvae_dsprites_all_hpc_vae',  func_name='metrics.factor_vae_metric.FactorVAEMetric',     dataset_dir='/project/xqzhu/disentangle_datasets/dsprites/dsprites_all_noshuffle_tfr', dataset_name='Dsprites', use_latents='[0,1,2,3,4]', batch_size=60, num_train=10000, num_eval=5000, num_variance_estimate=10000, has_label_place=True, drange_net=[0., 1.]),
    EasyDict(name='factorvae_dsprites_all_devcube2',  func_name='metrics.factor_vae_metric.FactorVAEMetric',     dataset_dir='/home/xqzhu/disentangle_datasets/dsprites/dsprites_all_noshuffle_tfr', dataset_name='Dsprites', use_latents='[0,1,2,3,4]', batch_size=60, num_train=10000, num_eval=5000, num_variance_estimate=10000),
    EasyDict(name='factorvae_dsprites_scalorixy',  func_name='metrics.factor_vae_metric.FactorVAEMetric',     dataset_dir='/mnt/hdd/Datasets/dsprites/dsprites_scalorixy_noshuffle_tfr', dataset_name='Dsprites', use_latents='[1,2,3,4]', batch_size=60, num_train=10000, num_eval=5000, num_variance_estimate=10000),
    EasyDict(name='factorvae_dsprites_scalorixy_devcube2',  func_name='metrics.factor_vae_metric.FactorVAEMetric',     dataset_dir='/home/xqzhu/disentangle_datasets/dsprites/dsprites_scalorixy_noshuffle_tfr', dataset_name='Dsprites', use_latents='[1,2,3,4]', batch_size=60, num_train=10000, num_eval=5000, num_variance_estimate=10000),
    EasyDict(name='factorvae_dsprites_scalxy',  func_name='metrics.factor_vae_metric.FactorVAEMetric',     dataset_dir='/mnt/hdd/Datasets/dsprites/dsprites_square_scalxy_noshuffle_tfr', dataset_name='Dsprites', use_latents='[1,3,4]', batch_size=60, num_train=10000, num_eval=5000, num_variance_estimate=10000),
    EasyDict(name='factorvae_dsprites_scalxy_devcube2',  func_name='metrics.factor_vae_metric.FactorVAEMetric',     dataset_dir='/home/xqzhu/disentangle_datasets/dsprites/dsprites_square_scalxy_noshuffle_tfr', dataset_name='Dsprites', use_latents='[1,3,4]', batch_size=60, num_train=10000, num_eval=5000, num_variance_estimate=10000),
    EasyDict(name='factorvae_shape3d_all',  func_name='metrics.factor_vae_metric.FactorVAEMetric',     dataset_dir='/mnt/hdd/Datasets/shapes_3d/shape3d_all_noshuffle_tfr', dataset_name='3DShapes', use_latents='[0,1,2,3,4,5]', batch_size=60, num_train=10000, num_eval=5000, num_variance_estimate=10000),
    EasyDict(name='factorvae_shape3d_all_hpc',  func_name='metrics.factor_vae_metric.FactorVAEMetric',     dataset_dir='/project/xqzhu/disentangle_datasets/shapes_3d/shape3d_all_noshuffle_tfr', dataset_name='3DShapes', use_latents='[0,1,2,3,4,5]', batch_size=60, num_train=10000, num_eval=5000, num_variance_estimate=10000),
    EasyDict(name='factorvae_shape3d_all_hpc_vae',  func_name='metrics.factor_vae_metric.FactorVAEMetric',     dataset_dir='/project/xqzhu/disentangle_datasets/shapes_3d/shape3d_all_noshuffle_tfr', dataset_name='3DShapes', use_latents='[0,1,2,3,4,5]', batch_size=60, num_train=10000, num_eval=5000, num_variance_estimate=10000, has_label_place=True, drange_net=[0., 1.]),
]])

#----------------------------------------------------------------------------
