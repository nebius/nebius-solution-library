# Copyright (c) 2022-2024, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import os
import hydra

from omegaconf.omegaconf import OmegaConf, open_dict
from pytorch_lightning import Trainer
from pytorch_lightning.callbacks.timer import Timer
import warnings
import torch

from nemo.collections.nlp.parts.nlp_overrides import (
    GradScaler,
    MegatronHalfPrecisionPlugin,
    PipelineMixedPrecisionPlugin,
)
from nemo.utils import logging
from nemo.utils.exp_manager import StatelessTimer, exp_manager, TimingCallback, NeMoModelCheckpoint
try:
    from lightning_lite.plugins.environments import TorchElasticEnvironment
except ImportError:
    from pytorch_lightning.plugins.environments import TorchElasticEnvironment

from benchmark import BenchmarkCallback
import custom_optimizer  # noqa (this import just registers a new optimizer)
import custom_schedulers  # noqa (this import just registers a new LR scheduler)
from custom_callbacks import CustomCallback, MetricsLogger, \
    DistributedCheckpointIO, \
    DeltaTimingCallback, EpochTimingCallback, CustomNLPDDPStrategy, CustomMegatronGPTModel, \
    configure_pre_validation_training_loop, setup_auxiliary_loggers
from mlperf_logger import mllogger
from types import MethodType
from pytorch_lightning.callbacks import ModelCheckpoint

from nemo.core.optim.optimizers import AVAILABLE_OPTIMIZERS
from custom_optimizer import CustomDistributedFusedAdam

OmegaConf.register_new_resolver("add", lambda x,y: x + y)
OmegaConf.register_new_resolver("ceil_div", lambda x,y: (x + y - 1)//y)
OmegaConf.register_new_resolver("floor_div", lambda x,y: x//y)
OmegaConf.register_new_resolver("div", lambda x,y: x/y)
OmegaConf.register_new_resolver("if", lambda x,y,z: y if x else z)
OmegaConf.register_new_resolver("lt", lambda x,y: x < y)
OmegaConf.register_new_resolver("eq", lambda x,y: x == y)
OmegaConf.register_new_resolver("neq", lambda x,y: x != y)
OmegaConf.register_new_resolver("or", lambda *args: any(args))

@hydra.main(config_path="conf", config_name="megatron_gpt_config_custom", version_base="1.2")
def main(cfg) -> None:
    # Suppress warnings
    warnings.filterwarnings("ignore")
    torch.set_warn_always(False)

    OmegaConf.resolve(cfg)

    if not cfg.model.mcore_gpt:
        AVAILABLE_OPTIMIZERS['distributed_fused_adam'] = CustomDistributedFusedAdam  # replace default implementation

    import logging as base_logging
    base_logging.getLogger("torch.distributed.distributed_c10d").setLevel(logging.WARNING)

    if cfg.model.nsys_profile.enabled and os.getenv('PROFILE_RANKS', '') != '':
        prof_ranks = [int(rank) for rank in os.getenv('PROFILE_RANKS').replace(" ", "").split(',')]
        cfg.model.nsys_profile.ranks = prof_ranks

    logging.info("\n\n************** Experiment configuration ***********")
    logging.info(f'\n{OmegaConf.to_yaml(cfg)}')

    # Disable most NeMo logging outputs
    if cfg.model.custom.get('disable_nemo_logs', True):
        logging.setLevel(50)

    megatron_amp_o2 = cfg.model.get('megatron_amp_O2', False)
    with_distributed_adam = cfg.model.optim.get('name') == 'distributed_fused_adam'

    plugins = [
        DistributedCheckpointIO(cfg.model.custom.get('load_directly_on_device', False),
                                cfg.model.custom.get('use_two_stage_loading', 0),
                                cfg.model.custom.get('use_two_stage_cpu_transfer', 1))
    ]


    load_strategy = 'directly_on_device' if cfg.model.custom.get('load_directly_on_device', False) else None
    load_strategy = 'two_stage' if cfg.model.custom.get('use_two_stage_loading', 0) else load_strategy

    strategy = CustomNLPDDPStrategy(
        use_dist_ckpt=cfg.model.custom.get('use_distributed_checkpointing', 1),
        mcore_gpt = cfg.model.mcore_gpt,
        checkpoint_load_strategy = load_strategy,
        no_ddp_communication_hook=True,  # we don't use DDP for async grad allreduce
        gradient_as_bucket_view=cfg.model.gradient_as_bucket_view,
        find_unused_parameters=False,
        nccl_communicator_config_path=cfg.model.nccl_communicator_config_path,
        sharp=cfg.model.sharp,
    )

    if cfg.trainer.precision in [16, '16', 'bf16', '16-mixed', 'bf16-mixed']:
        scaler = None
        if cfg.trainer.precision in [16, '16', '16-mixed']:
            scaler = GradScaler(
                init_scale=cfg.model.get('native_amp_init_scale', 2 ** 32),
                growth_interval=cfg.model.get('native_amp_growth_interval', 1000),
                hysteresis=cfg.model.get('hysteresis', 2),
            )
            # MixedPrecisionPlugin in PTL >= 2.0 requires precision to be 16-mixed or bf16-mixed
            plugin_precision = '16-mixed'
        else:
            plugin_precision = 'bf16-mixed'

        if megatron_amp_o2 and not with_distributed_adam:
            plugins.append(MegatronHalfPrecisionPlugin(precision=plugin_precision, device='cuda', scaler=scaler))
        else:
            plugins.append(PipelineMixedPrecisionPlugin(precision=plugin_precision, device='cuda', scaler=scaler))

        cfg.trainer.precision = None

    #    if cfg.get('cluster_type', None) == 'BCP':
    #        plugins.append(TorchElasticEnvironment())
    plugins.append(TorchElasticEnvironment())

    custom_callback = CustomCallback(cfg)
    callbacks = [custom_callback]

    benchmark_callback = None
    if cfg.exp_manager.create_mlflow_logger:
        benchmark_callback = BenchmarkCallback(cfg)
        callbacks.append(benchmark_callback)

    trainer = Trainer(
        plugins=plugins, strategy=strategy, **cfg.trainer, callbacks=callbacks
    )

    exp_manager(trainer, cfg.exp_manager)
    setup_auxiliary_loggers()

    # Override timer callback to a stateless one
    for idx, callback in enumerate(trainer.callbacks):
        if isinstance(callback, Timer):
            trainer.callbacks[idx] = StatelessTimer(cfg.trainer.max_time,)
        if isinstance(callback, TimingCallback):
            if cfg.model.custom.log_metrics == 'NEMO':
                trainer.callbacks[idx] = EpochTimingCallback(callback.timer)
            elif cfg.model.custom.log_metrics == 'DELTA':
                trainer.callbacks[idx] = DeltaTimingCallback()
            else:
                del trainer.callbacks[idx]
        if isinstance(callback, NeMoModelCheckpoint):
            # In the exp_manager, configure_checkpoint: https://github.com/NVIDIA/NeMo/blob/main/nemo/utils/exp_manager.py#L1022 method
            # is called which manipulates the configuration parameters before creating the NemoModelCheckpoint instance.
            # Using the workaround below to avoid that
            def custom_on_validation_end(self, trainer: "pl.Trainer", pl_module: "pl.LightningModule"):
                pass
            def custom_on_train_end(self, trainer: "pl.Trainer", pl_module: "pl.LightningModule"):
                if trainer.fast_dev_run:
                    return None
                monitor_candidates = self._monitor_candidates(trainer)
                ModelCheckpoint._save_last_checkpoint(self, trainer, monitor_candidates)
                # Call parent on_train_end() to save the -last checkpoint
                ModelCheckpoint.on_train_end(self, trainer, pl_module)
            if cfg.exp_manager.get('checkpoint_callback_params', None) and (cfg.exp_manager.checkpoint_callback_params.get('every_n_epochs', 1) == 0):
                trainer.callbacks[idx].on_validation_end = MethodType(custom_on_validation_end, trainer.callbacks[idx])
            if cfg.exp_manager.get('checkpoint_callback_params', None) and cfg.exp_manager.checkpoint_callback_params.get('save_last', False):
                trainer.callbacks[idx].on_train_end = MethodType(custom_on_train_end, trainer.callbacks[idx])

    # hydra interpolation does not work here as the interpolation key is lost when PTL saves hparams
    with open_dict(cfg):
        cfg.model.precision = cfg.trainer.precision

    model = CustomMegatronGPTModel(cfg.model, trainer)

    trainer.loggers.append(
        MetricsLogger(
            trainer,
            model,
            custom_callback,
            cfg.model.custom.target_log_ppl,
            cfg.model.custom.extend_run_evals,
            benchmark_callback=benchmark_callback,
        )
    )

    if cfg.model.custom.pre_validate:
        configure_pre_validation_training_loop(trainer)

    logging.info(f'Resuming training from checkpoint: {cfg.model.resume_from_checkpoint}')
    s = torch.cuda.Stream()
    torch.cuda.set_stream(s)
    trainer.fit(model, ckpt_path=cfg.model.resume_from_checkpoint)


if __name__ == '__main__':
    mllogger.start(key=mllogger.constants.INIT_START)
    main()
