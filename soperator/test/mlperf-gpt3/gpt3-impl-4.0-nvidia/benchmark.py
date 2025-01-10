import os
from dataclasses import dataclass, field
from datetime import datetime as DateTime
from datetime import timedelta as TimeDelta
from enum import Enum
from typing import Any, Optional, Sequence

import mlflow.entities as mlf
import pandas as pd
from pytorch_lightning import Callback, LightningModule, Trainer
from pytorch_lightning.loggers import MLFlowLogger
from pytorch_lightning.utilities import rank_zero_only
from pytorch_lightning.utilities.types import STEP_OUTPUT

from custom_callbacks import WarmupDurationMetrics, compute_consumed_mllog_tokens


@dataclass
class BenchmarkParams:
    # fmt: off

    training_samples:       int = 0
    training_block_size:    int = 0
    training_block_samples: int = 0
    training_step_samples:  int = 0

    validation_samples:       int = 0
    validation_block_size:    Optional[int] = None
    validation_block_samples: int = 0
    validation_step_samples:  Optional[int] = None

    sequence_size: int = 0

    # fmt: on


class BenchmarkKeys(str, Enum):
    # fmt: off

    BENCHMARK               = 'benchmark'
    STAT_MEAN               = 'mean'
    STAT_STD                = 'std'
    STAT_MEDIAN             = 'median'
    STAT_PERC_75            = 'p75'

    PARAM_TRAINING_SAMPLES           = f'{BENCHMARK}/training/samples'
    PARAM_TRAINING_BLOCK_SIZE        = f'{BENCHMARK}/training/block/size'
    PARAM_TRAINING_BLOCK_SAMPLES     = f'{BENCHMARK}/training/block/samples'
    PARAM_TRAINING_STEP_SAMPLES      = f'{BENCHMARK}/training/step/samples'
    PARAM_VALIDATION_SAMPLES         = f'{BENCHMARK}/validation/samples'
    PARAM_VALIDATION_BLOCK_SIZE      = f'{BENCHMARK}/validation/block/size'
    PARAM_VALIDATION_BLOCK_SAMPLES   = f'{BENCHMARK}/validation/block/samples'
    PARAM_VALIDATION_STEP_SAMPLES    = f'{BENCHMARK}/validation/step/samples'
    PARAM_SEQUENCE_SIZE              = f'{BENCHMARK}/sequence/size'

    METRIC_DURATION_TIME_TO_RUN       = f'{BENCHMARK}/duration/timeToRun'
    METRIC_DURATION_TOTAL             = f'{BENCHMARK}/duration/total'
    METRIC_DURATION_INITIALIZATION    = f'{BENCHMARK}/duration/initialization'
    METRIC_DURATION_WARMUP_CUDAGRAPH  = f'{BENCHMARK}/duration/warmup/cudagraph'
    METRIC_DURATION_WARMUP_TRAINING   = f'{BENCHMARK}/duration/warmup/training'
    METRIC_DURATION_WARMUP_VALIDATION = f'{BENCHMARK}/duration/warmup/validation'
    METRIC_DURATION_TRAINING          = f'{BENCHMARK}/duration/training'
    METRIC_DURATION_TRAINING_BLOCK    = f'{BENCHMARK}/duration/training/block'
    METRIC_DURATION_VALIDATION_BLOCK  = f'{BENCHMARK}/duration/validation/block'

    METRIC_SAMPLES_PER_SECOND_TRAINING_EPOCH   = f'{BENCHMARK}/samplesPerSecond/training/epoch'
    METRIC_SAMPLES_PER_SECOND_TRAINING_BLOCK   = f'{BENCHMARK}/samplesPerSecond/training/block'
    METRIC_SAMPLES_PER_SECOND_TRAINING_STEP    = f'{BENCHMARK}/samplesPerSecond/training/step'
    METRIC_SAMPLES_PER_SECOND_VALIDATION_BLOCK = f'{BENCHMARK}/samplesPerSecond/validation/block'
    METRIC_SAMPLES_PER_SECOND_VALIDATION_STEP  = f'{BENCHMARK}/samplesPerSecond/validation/step'

    # fmt: on

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return self.value


@dataclass
class MetricKV:
    key: str
    value: float


@dataclass
class DelayedMetricKV(MetricKV):
    timestamp: Optional[int] = None
    step: Optional[int] = None


@dataclass
class StepMetrics:
    training: list[mlf.Metric] = field(default_factory=list)
    validation: list[mlf.Metric] = field(default_factory=list)


@dataclass
class ParamKV:
    key: str
    value: str


@dataclass
class Statistics:
    last: float
    mean: float
    std: float
    median: float
    p75: float


@dataclass
class MetricMixin:
    metric_name: str


@dataclass
class StatisticsMixin(MetricMixin):
    _records: list[float] = field(default_factory=list)

    @property
    def statistics(self) -> Statistics:
        if len(self._records) == 0:
            return Statistics(
                last=0.0,
                mean=0.0,
                std=0.0,
                median=0.0,
                p75=0.0,
            )

        s = pd.Series(self._records, dtype=float)
        median, p75 = list(s.quantile([0.5, 0.75]))
        return Statistics(
            last=s.iloc[-1],
            mean=s.mean(),
            std=s.std(),
            median=median,
            p75=p75,
        )

    @property
    def stat_metrics(self) -> Sequence[MetricKV]:
        if len(self._records) == 0:
            return []

        statistics = self.statistics
        res = [
            MetricKV(
                key=self.metric_name,
                value=statistics.last,
            )
        ]

        for key in [
            BenchmarkKeys.STAT_MEAN.value,
            BenchmarkKeys.STAT_STD.value,
            BenchmarkKeys.STAT_MEDIAN.value,
            BenchmarkKeys.STAT_PERC_75.value,
        ]:
            res.append(
                MetricKV(
                    key=f'{self.metric_name}_{key}',
                    value=getattr(statistics, key),
                )
            )

        return res


@dataclass
class SingleShotDurationMetric(MetricMixin):
    _duration: TimeDelta = DateTime.now()

    def update(self, duration: TimeDelta) -> None:
        self._duration = duration

    @property
    def elapsed_seconds(self) -> float:
        return self._duration.total_seconds()


@dataclass
class BlockDurationMetric(StatisticsMixin):
    _initial_timestamp: DateTime = DateTime.now()
    _elapsed_time: TimeDelta = TimeDelta()

    def reset(self, initial_timestamp: DateTime) -> None:
        self._initial_timestamp = initial_timestamp
        self._elapsed_time = TimeDelta()

    def update(self, timestamp: DateTime) -> None:
        self._elapsed_time = timestamp - self._initial_timestamp

        self._records.append(self._elapsed_time.total_seconds())

    @property
    def elapsed_seconds(self) -> float:
        return self._elapsed_time.total_seconds()


@dataclass
class BlockSamplesPerSecondMetric(StatisticsMixin):
    _timestamp_start: DateTime = DateTime.now()
    _timestamp_end: DateTime = DateTime.now()
    _consumed_samples_start: int = 0
    _consumed_samples_end: int = 0

    def start(self, timestamp: DateTime, consumed: Optional[int] = None) -> None:
        self._timestamp_start = timestamp
        self._timestamp_end = timestamp
        self._consumed_samples_start = consumed or self._consumed_samples_end

    def stop(self, timestamp: DateTime, consumed_samples: int) -> None:
        self._timestamp_end = timestamp
        self._consumed_samples_end = consumed_samples

        samples_per_block = self._consumed_samples_end - self._consumed_samples_start
        duration = self._timestamp_end - self._timestamp_start

        self._records.append(samples_per_block / duration.total_seconds())


@dataclass
class StepSamplesPerSecondMetric(StatisticsMixin):
    def append(self, value: float) -> None:
        self._records.append(value)


@dataclass
class BenchmarkMetrics:
    # fmt: off

    time_to_run_duration = SingleShotDurationMetric(BenchmarkKeys.METRIC_DURATION_TIME_TO_RUN.value)

    total_duration            = BlockDurationMetric(BenchmarkKeys.METRIC_DURATION_TOTAL.value)
    initialization_duration   = BlockDurationMetric(BenchmarkKeys.METRIC_DURATION_INITIALIZATION.value)
    training_duration         = BlockDurationMetric(BenchmarkKeys.METRIC_DURATION_TRAINING.value)
    training_block_duration   = BlockDurationMetric(BenchmarkKeys.METRIC_DURATION_VALIDATION_BLOCK.value)
    validation_block_duration = BlockDurationMetric(BenchmarkKeys.METRIC_DURATION_VALIDATION_BLOCK.value)

    training_epoch_samples_per_second  = BlockSamplesPerSecondMetric(BenchmarkKeys.METRIC_SAMPLES_PER_SECOND_TRAINING_EPOCH.value)
    training_block_samples_per_second  = BlockSamplesPerSecondMetric(BenchmarkKeys.METRIC_SAMPLES_PER_SECOND_TRAINING_BLOCK.value)
    validation_block_samples_per_second = BlockSamplesPerSecondMetric(BenchmarkKeys.METRIC_SAMPLES_PER_SECOND_VALIDATION_BLOCK.value)

    training_step_samples_per_second   = StepSamplesPerSecondMetric(BenchmarkKeys.METRIC_SAMPLES_PER_SECOND_TRAINING_STEP.value)
    validation_step_samples_per_second = StepSamplesPerSecondMetric(BenchmarkKeys.METRIC_SAMPLES_PER_SECOND_VALIDATION_STEP.value)

    # fmt: on


class BenchmarkCallback(Callback):
    ENV_VAR_TIMING_START_TIME = 'MLF_VALUE_TIMING_START_TIME'

    STEP_TIMING_KEY_TRAINING = 'train_step_timing in s'
    STEP_TIMING_KEY_VALIDATION = 'validation_step_timing in s'

    def __init__(self, cfg):
        super().__init__()

        self.params: BenchmarkParams = self._calculate_params(cfg)
        self.metrics: BenchmarkMetrics = BenchmarkMetrics()
        self.step_metrics: StepMetrics = StepMetrics()

        self.warmup_metrics: list[DelayedMetricKV] = []

    @staticmethod
    def _calculate_params(cfg) -> BenchmarkParams:
        res = BenchmarkParams()

        global_batch_size = cfg.model.global_batch_size
        max_train_steps = cfg.trainer.max_steps
        val_check_interval = cfg.trainer.val_check_interval
        eval_iters = int((max_train_steps // val_check_interval + 1) * cfg.trainer.limit_val_batches)

        res.training_samples = max_train_steps * global_batch_size
        res.training_block_size = val_check_interval
        res.training_block_samples = res.training_block_size * global_batch_size
        res.training_step_samples = global_batch_size

        res.validation_samples = eval_iters * global_batch_size
        res.validation_block_samples = res.validation_samples

        res.sequence_size = cfg.model.data.seq_length

        return res

    @rank_zero_only
    def on_fit_start(self, trainer: Trainer, pl_module: LightningModule) -> None:
        now = DateTime.now()
        self.metrics.time_to_run_duration.update(
            now
            - DateTime.fromtimestamp(int(os.environ.get(self.ENV_VAR_TIMING_START_TIME, default=int(now.timestamp()))))
        )

        self.metrics.total_duration.reset(now)
        self.metrics.initialization_duration.reset(now)

        self.log_metrics(
            trainer,
            [
                MetricKV(
                    key=self.metrics.time_to_run_duration.metric_name,
                    value=self.metrics.time_to_run_duration.elapsed_seconds,
                )
            ],
            timestamp=now,
            params=[
                ParamKV(
                    key=BenchmarkKeys.PARAM_TRAINING_SAMPLES.value,
                    value=str(self.params.training_samples),
                ),
                ParamKV(
                    key=BenchmarkKeys.PARAM_TRAINING_BLOCK_SIZE.value,
                    value=str(self.params.training_block_size),
                ),
                ParamKV(
                    key=BenchmarkKeys.PARAM_TRAINING_BLOCK_SAMPLES.value,
                    value=str(self.params.training_block_samples),
                ),
                ParamKV(
                    key=BenchmarkKeys.PARAM_TRAINING_STEP_SAMPLES.value,
                    value=str(self.params.training_step_samples),
                ),
                ParamKV(
                    key=BenchmarkKeys.PARAM_VALIDATION_SAMPLES.value,
                    value=str(self.params.validation_samples),
                ),
                ParamKV(
                    key=BenchmarkKeys.PARAM_VALIDATION_BLOCK_SAMPLES.value,
                    value=str(self.params.validation_block_samples),
                ),
                ParamKV(
                    key=BenchmarkKeys.PARAM_SEQUENCE_SIZE.value,
                    value=str(self.params.sequence_size),
                ),
            ],
        )

    @rank_zero_only
    def on_fit_end(self, trainer: Trainer, pl_module: LightningModule) -> None:
        now = DateTime.now()
        self.log_metrics(
            trainer,
            [self._update_duration_metric(self.metrics.total_duration, now)],
            timestamp=now,
        )

    @rank_zero_only
    def on_train_start(self, trainer: Trainer, pl_module: LightningModule) -> None:
        now = DateTime.now()
        self.metrics.training_duration.reset(now)
        self.log_metrics(
            trainer,
            metrics=[
                self._update_duration_metric(self.metrics.initialization_duration, now),
                self._update_duration_metric(self.metrics.training_duration, now),
            ],
            timestamp=now,
        )

    @rank_zero_only
    def on_train_end(self, trainer: Trainer, pl_module: LightningModule) -> None:
        now = DateTime.now()
        self.log_metrics(
            trainer,
            metrics=[
                self._update_duration_metric(self.metrics.training_duration, now),
            ],
            timestamp=now,
            with_duration_metrics=[self.metrics.total_duration],
        )

    @rank_zero_only
    def on_train_epoch_start(self, trainer: Trainer, pl_module: LightningModule) -> None:
        self.metrics.training_epoch_samples_per_second.start(DateTime.now())

    @rank_zero_only
    def on_train_epoch_end(self, trainer: Trainer, pl_module: LightningModule) -> None:
        now = DateTime.now()
        self.metrics.training_epoch_samples_per_second.stop(
            now, compute_consumed_mllog_tokens(trainer, pl_module) / self.params.sequence_size
        )
        self.log_metrics(
            trainer,
            metrics=self.metrics.training_epoch_samples_per_second.stat_metrics,
            timestamp=now,
        )

    def _process_warmup_metrics(self, trainer: Trainer, timestamp: DateTime) -> None:
        if len(self.warmup_metrics) == 0:
            return

        self.log_metrics(
            trainer,
            metrics=[],
            timestamp=timestamp,
            warmup_metrics=self.warmup_metrics,
        )
        self.warmup_metrics.clear()

    @rank_zero_only
    def on_train_batch_start(
        self,
        trainer: Trainer,
        pl_module: LightningModule,
        batch: Any,
        batch_idx: int,
    ) -> None:
        now = DateTime.now()
        self.metrics.training_block_duration.reset(now)
        self.metrics.training_block_samples_per_second.start(now, 0)
        self._process_training_step_metrics(trainer, now)
        self._process_warmup_metrics(trainer, now)

    @rank_zero_only
    def on_train_batch_end(
        self,
        trainer: Trainer,
        pl_module: LightningModule,
        outputs: STEP_OUTPUT,
        batch: Any,
        batch_idx: int,
    ) -> None:
        now = DateTime.now()
        self._update_duration_metric(self.metrics.training_block_duration, now)
        self.metrics.training_block_samples_per_second.stop(now, self.params.training_block_samples)

        self.log_metrics(
            trainer,
            metrics=[
                *self.metrics.training_block_duration.stat_metrics,
                *self.metrics.training_block_samples_per_second.stat_metrics,
            ],
            timestamp=now,
            with_duration_metrics=[
                self.metrics.total_duration,
                self.metrics.training_duration,
            ],
        )

        self._process_training_step_metrics(trainer, now)

    def _process_training_step_metrics(self, trainer: Trainer, timestamp: DateTime) -> None:
        if len(self.step_metrics.training) == 0:
            return

        step_samples_per_second: list[mlf.Metric] = []
        for metric in self.step_metrics.training:
            step_samples_per_second.append(metric)
            self.metrics.training_step_samples_per_second.append(metric.value)
            for stat in self.metrics.training_step_samples_per_second.stat_metrics:
                step_samples_per_second.append(
                    mlf.Metric(
                        key=stat.key,
                        value=stat.value,
                        timestamp=metric.timestamp,
                        step=metric.step,
                    )
                )
        self.step_metrics.training.clear()

    @rank_zero_only
    def on_validation_start(self, trainer: Trainer, pl_module: LightningModule) -> None:
        now = DateTime.now()
        self.metrics.validation_block_duration.reset(now)
        self.metrics.validation_block_samples_per_second.start(now, 0)
        self._process_validation_step_metrics(trainer, now)

    @rank_zero_only
    def on_validation_end(self, trainer: Trainer, pl_module: LightningModule) -> None:
        now = DateTime.now()
        self._update_duration_metric(self.metrics.validation_block_duration, now)
        self.metrics.validation_block_samples_per_second.stop(now, self.params.validation_block_samples)

        self.log_metrics(
            trainer,
            metrics=[
                *self.metrics.validation_block_duration.stat_metrics,
                *self.metrics.validation_block_samples_per_second.stat_metrics,
            ],
            timestamp=now,
            with_duration_metrics=[
                self.metrics.total_duration,
            ],
        )

        self._process_validation_step_metrics(trainer, now)

    def _process_validation_step_metrics(self, trainer: Trainer, timestamp: DateTime) -> None:
        if len(self.step_metrics.validation) == 0:
            return

        params: Optional[list[ParamKV]] = None
        if self.params.validation_block_size is None:
            self.params.validation_block_size = len(self.step_metrics.validation)
            self.params.validation_step_samples = self.params.validation_samples // self.params.validation_block_size

            params = [
                ParamKV(
                    key=BenchmarkKeys.PARAM_VALIDATION_BLOCK_SIZE.value,
                    value=str(self.params.validation_block_size),
                ),
                ParamKV(
                    key=BenchmarkKeys.PARAM_VALIDATION_STEP_SAMPLES.value,
                    value=str(self.params.validation_step_samples),
                ),
            ]

        step_samples_per_second: list[mlf.Metric] = []
        for metric in self.step_metrics.validation:
            metric = mlf.Metric(
                key=metric.key,
                value=self.params.validation_step_samples / metric.value,
                timestamp=metric.timestamp,
                step=metric.step,
            )
            step_samples_per_second.append(metric)
            self.metrics.validation_step_samples_per_second.append(metric.value)
            for stat in self.metrics.validation_step_samples_per_second.stat_metrics:
                step_samples_per_second.append(
                    mlf.Metric(
                        key=stat.key,
                        value=stat.value,
                        timestamp=metric.timestamp,
                        step=metric.step,
                    )
                )
        self.step_metrics.validation.clear()

        self.log_metrics(
            trainer,
            metrics=[],
            timestamp=timestamp,
            params=params,
            raw_metrics=step_samples_per_second,
        )

    @rank_zero_only
    def on_external_log_metrics(self, metrics: dict[str, float], step: Optional[int]) -> None:
        if self.STEP_TIMING_KEY_TRAINING in metrics:
            m = mlf.Metric(
                key=BenchmarkKeys.METRIC_SAMPLES_PER_SECOND_TRAINING_STEP.value,
                value=self.params.training_step_samples / metrics[self.STEP_TIMING_KEY_TRAINING],
                timestamp=DateTime.now().microsecond // 1000,
                step=step,
            )
            self.step_metrics.training.append(m)
            return

        if self.STEP_TIMING_KEY_VALIDATION in metrics:
            m = mlf.Metric(
                key=BenchmarkKeys.METRIC_SAMPLES_PER_SECOND_VALIDATION_STEP.value,
                # temporary value while we don't know the number of validation steps
                value=metrics[self.STEP_TIMING_KEY_VALIDATION],
                timestamp=DateTime.now().microsecond // 1000,
                step=step,
            )
            self.step_metrics.validation.append(m)
            return

    @rank_zero_only
    def log_warmup_duration_metrics(self, warmup_metrics: WarmupDurationMetrics, step: Optional[int]) -> None:
        now = DateTime.now()
        timestamp = now.microsecond // 1000
        self.warmup_metrics.extend(
            [
                DelayedMetricKV(
                    key=metric_name,
                    value=metric_value,
                    timestamp=timestamp,
                    step=step,
                )
                for metric_name, metric_value in (
                    (BenchmarkKeys.METRIC_DURATION_WARMUP_CUDAGRAPH.value, warmup_metrics.cudagraph),
                    (BenchmarkKeys.METRIC_DURATION_WARMUP_TRAINING.value, warmup_metrics.training),
                    (BenchmarkKeys.METRIC_DURATION_WARMUP_VALIDATION.value, warmup_metrics.validation),
                )
            ]
        )

    @staticmethod
    def log_metrics(
        trainer: Trainer,
        metrics: Sequence[MetricKV],
        timestamp: DateTime,
        params: Optional[Sequence[ParamKV]] = None,
        raw_metrics: Optional[Sequence[mlf.Metric]] = None,
        warmup_metrics: Optional[list[DelayedMetricKV]] = None,
        with_duration_metrics: Optional[Sequence[BlockDurationMetric]] = None,
    ) -> None:
        logger = BenchmarkCallback._get_mlflow_logger(trainer)
        if logger is None:
            return

        if with_duration_metrics is not None:
            metrics = list(metrics) + [
                BenchmarkCallback._update_duration_metric(metric, timestamp) for metric in with_duration_metrics
            ]

        full_metrics = [
            mlf.Metric(
                key=metric.key,
                value=metric.value,
                timestamp=timestamp.microsecond // 1000,
                step=trainer.global_step,
            )
            for metric in metrics
        ]

        if warmup_metrics is not None and len(warmup_metrics) > 0:
            full_metrics.extend(
                [
                    mlf.Metric(
                        key=metric.key,
                        value=metric.value,
                        timestamp=metric.timestamp if metric.timestamp is not None else timestamp.microsecond // 1000,
                        step=metric.step if metric.step is not None else trainer.global_step,
                    )
                    for metric in warmup_metrics
                ]
            )

        if raw_metrics is not None and len(raw_metrics) > 0:
            full_metrics.extend(raw_metrics)

        logger.experiment.log_batch(
            run_id=logger.run_id,
            metrics=full_metrics,
            params=([mlf.Param(key=param.key, value=param.value) for param in params] if params else ()),
            synchronous=True,
        )

        if warmup_metrics is not None and len(warmup_metrics) > 0:
            warmup_metrics.clear()

    @staticmethod
    def _get_mlflow_logger(trainer: Trainer) -> Optional[MLFlowLogger]:
        for logger in trainer.loggers:
            if isinstance(logger, MLFlowLogger):
                return logger
        return None

    @staticmethod
    def _update_duration_metric(metric: BlockDurationMetric, timestamp: DateTime) -> MetricKV:
        metric.update(timestamp)

        return MetricKV(
            key=metric.metric_name,
            value=metric.elapsed_seconds,
        )
