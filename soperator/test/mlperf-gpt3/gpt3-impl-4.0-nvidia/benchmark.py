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

from custom_callbacks import compute_consumed_mllog_tokens


@dataclass
class BenchmarkParams:
    training_block_size: int = 0
    samples_per_training_block: int = 0
    samples_per_training_step: int = 0


class BenchmarkKeys(str, Enum):
    BENCHMARK = 'benchmark'
    UNIT_SECONDS = 's'
    UNIT_SAMPLES_PER_SECOND = 'samples/s'
    STAT_MEAN = 'mean'
    STAT_STD = 'std'
    STAT_MEDIAN = 'median'
    STAT_PERC_75 = 'p75'

    PARAM_TRAINING_BLOCK_SIZE = f'{BENCHMARK}/training_block_size'
    PARAM_SAMPLES_PER_TRAINING_BLOCK = f'{BENCHMARK}/samples_per_training_block'
    PARAM_SAMPLES_PER_TRAINING_STEP = f'{BENCHMARK}/samples_per_training_step'

    METRIC_TIME_TO_RUN_DURATION = f'{BENCHMARK}.timeToRun.duration_{UNIT_SECONDS}'
    METRIC_TOTAL_RUNTIME_DURATION = f'{BENCHMARK}.totalRuntime.duration_{UNIT_SECONDS}'
    METRIC_TRAINING_DURATION = f'{BENCHMARK}.training.duration_{UNIT_SECONDS}'
    METRIC_INITIALIZATION_DURATION = f'{BENCHMARK}.initialization.duration_{UNIT_SECONDS}'

    METRIC_EPOCH_SAMPLES_PER_SECOND = f'{BENCHMARK}.epoch_{UNIT_SAMPLES_PER_SECOND}'
    METRIC_TRAINING_BLOCK_SAMPLES_PER_SECOND = f'{BENCHMARK}.trainingBlock_{UNIT_SAMPLES_PER_SECOND}'
    METRIC_TRAINING_STEP_SAMPLES_PER_SECOND = f'{BENCHMARK}.trainingStep_{UNIT_SAMPLES_PER_SECOND}'
    METRIC_VALIDATION_BLOCK_DURATION = f'{BENCHMARK}.validationBlock.duration_{UNIT_SECONDS}'
    METRIC_VALIDATION_STEP_SAMPLES_PER_SECOND = f'{BENCHMARK}.validationStep_{UNIT_SAMPLES_PER_SECOND}'

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return self.value


@dataclass
class MetricKV:
    key: str
    value: float


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
class DurationMetric(StatisticsMixin):
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
class SamplesPerSecondMetric(StatisticsMixin):
    _timestamp_start: DateTime = DateTime.now()
    _timestamp_end: DateTime = DateTime.now()
    _consumed_samples_start: int = 0
    _consumed_samples_end: int = 0

    def start(self, timestamp: DateTime) -> None:
        self._timestamp_start = timestamp
        self._timestamp_end = timestamp
        self._consumed_samples_start = self._consumed_samples_end

    def stop(self, timestamp: DateTime, consumed_samples: int) -> None:
        self._timestamp_end = timestamp
        self._consumed_samples_end = consumed_samples

        samples_per_block = self._consumed_samples_end - self._consumed_samples_start
        duration = self._timestamp_end - self._timestamp_start

        self._records.append(samples_per_block / duration.total_seconds())


@dataclass
class BenchmarkMetrics:
    time_to_run: DurationMetric = DurationMetric(metric_name=BenchmarkKeys.METRIC_TIME_TO_RUN_DURATION.value)
    total_runtime_duration: DurationMetric = DurationMetric(
        metric_name=BenchmarkKeys.METRIC_TOTAL_RUNTIME_DURATION.value
    )
    training_duration: DurationMetric = DurationMetric(metric_name=BenchmarkKeys.METRIC_TRAINING_DURATION.value)
    initialization_duration: DurationMetric = DurationMetric(
        metric_name=BenchmarkKeys.METRIC_INITIALIZATION_DURATION.value
    )

    metric_epoch_samples_per_second: SamplesPerSecondMetric = SamplesPerSecondMetric(
        metric_name=BenchmarkKeys.METRIC_EPOCH_SAMPLES_PER_SECOND.value
    )
    metric_training_block_samples_per_second: SamplesPerSecondMetric = SamplesPerSecondMetric(
        metric_name=BenchmarkKeys.METRIC_TRAINING_BLOCK_SAMPLES_PER_SECOND.value
    )
    metric_training_step_samples_per_second: SamplesPerSecondMetric = SamplesPerSecondMetric(
        metric_name=BenchmarkKeys.METRIC_TRAINING_STEP_SAMPLES_PER_SECOND.value
    )
    metric_validation_block_duration: DurationMetric = DurationMetric(
        metric_name=BenchmarkKeys.METRIC_VALIDATION_BLOCK_DURATION.value
    )
    metric_validation_step_samples_per_second: SamplesPerSecondMetric = SamplesPerSecondMetric(
        metric_name=BenchmarkKeys.METRIC_VALIDATION_STEP_SAMPLES_PER_SECOND.value
    )


class BenchmarkCallback(Callback):
    ENV_VAR_TIMING_START_TIME = 'MLF_VALUE_TIMING_START_TIME'

    def __init__(self, cfg):
        super().__init__()

        self.params: BenchmarkParams = BenchmarkParams(
            training_block_size=cfg.trainer.val_check_interval,
            samples_per_training_block=(
                cfg.trainer.val_check_interval * cfg.model.global_batch_size * cfg.model.encoder_seq_length
            ),
            samples_per_training_step=cfg.model.global_batch_size * cfg.model.encoder_seq_length,
        )
        self.metrics: BenchmarkMetrics = BenchmarkMetrics()

    @rank_zero_only
    def on_fit_start(self, trainer: Trainer, pl_module: LightningModule) -> None:
        now = DateTime.now()
        self.metrics.time_to_run.reset(
            DateTime.fromtimestamp(int(os.environ.get(self.ENV_VAR_TIMING_START_TIME, default=int(now.timestamp()))))
        )
        self.metrics.total_runtime_duration.reset(now)
        self.metrics.initialization_duration.reset(now)

        self.log_metrics(
            trainer,
            [self._update_duration_metric(self.metrics.time_to_run, now)],
            timestamp=now,
            params=[
                ParamKV(
                    key=BenchmarkKeys.PARAM_TRAINING_BLOCK_SIZE.value,
                    value=str(self.params.training_block_size),
                ),
                ParamKV(
                    key=BenchmarkKeys.PARAM_SAMPLES_PER_TRAINING_BLOCK.value,
                    value=str(self.params.samples_per_training_block),
                ),
                ParamKV(
                    key=BenchmarkKeys.PARAM_SAMPLES_PER_TRAINING_STEP.value,
                    value=str(self.params.samples_per_training_step),
                ),
            ],
        )

    @rank_zero_only
    def on_fit_end(self, trainer: Trainer, pl_module: LightningModule) -> None:
        now = DateTime.now()
        self.log_metrics(
            trainer,
            [self._update_duration_metric(self.metrics.total_runtime_duration, now)],
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
            with_duration_metrics=[self.metrics.total_runtime_duration],
        )

    @rank_zero_only
    def on_train_epoch_start(self, trainer: Trainer, pl_module: LightningModule) -> None:
        self.metrics.metric_epoch_samples_per_second.start(DateTime.now())

    @rank_zero_only
    def on_train_epoch_end(self, trainer: Trainer, pl_module: LightningModule) -> None:
        now = DateTime.now()
        self.metrics.metric_epoch_samples_per_second.stop(now, compute_consumed_mllog_tokens(trainer, pl_module))
        self.log_metrics(
            trainer,
            metrics=self.metrics.metric_epoch_samples_per_second.stat_metrics,
            timestamp=now,
        )

    @rank_zero_only
    def on_train_batch_start(
        self,
        trainer: Trainer,
        pl_module: LightningModule,
        batch: Any,
        batch_idx: int,
    ) -> None:
        self.metrics.metric_training_block_samples_per_second.start(DateTime.now())

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
        self.metrics.metric_training_block_samples_per_second.stop(
            now, compute_consumed_mllog_tokens(trainer, pl_module)
        )
        self.log_metrics(
            trainer,
            metrics=self.metrics.metric_training_block_samples_per_second.stat_metrics,
            timestamp=now,
            with_duration_metrics=[
                self.metrics.total_runtime_duration,
                self.metrics.training_duration,
            ],
        )

    @rank_zero_only
    def on_validation_start(self, trainer: Trainer, pl_module: LightningModule) -> None:
        self.metrics.metric_validation_block_duration.reset(DateTime.now())

    @rank_zero_only
    def on_validation_end(self, trainer: Trainer, pl_module: LightningModule) -> None:
        now = DateTime.now()
        self._update_duration_metric(self.metrics.metric_validation_block_duration, now)
        self.log_metrics(
            trainer,
            metrics=self.metrics.metric_validation_block_duration.stat_metrics,
            timestamp=now,
        )

    def log_metrics(
        self,
        trainer: Trainer,
        metrics: Sequence[MetricKV],
        timestamp: DateTime,
        params: Optional[Sequence[ParamKV]] = None,
        with_duration_metrics: Optional[Sequence[DurationMetric]] = None,
    ) -> None:
        logger = BenchmarkCallback._get_mlflow_logger(trainer)
        if logger is None:
            return

        if with_duration_metrics is not None:
            metrics = list(metrics) + [
                self._update_duration_metric(metric, timestamp) for metric in with_duration_metrics
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

        logger.experiment.log_batch(
            run_id=logger.run_id,
            metrics=full_metrics,
            params=([mlf.Param(key=param.key, value=param.value) for param in params] if params else ()),
        )

    @staticmethod
    def _get_mlflow_logger(trainer: Trainer) -> Optional[MLFlowLogger]:
        for logger in trainer.loggers:
            if isinstance(logger, MLFlowLogger):
                return logger
        return None

    @staticmethod
    def _update_duration_metric(metric: DurationMetric, timestamp: DateTime) -> MetricKV:
        metric.update(timestamp)

        return MetricKV(
            key=metric.metric_name,
            value=metric.elapsed_seconds,
        )
