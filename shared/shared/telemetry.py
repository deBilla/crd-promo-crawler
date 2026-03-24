"""OpenTelemetry instrumentation setup for all crawler services.

Provides metrics, traces, and logs export to the OTel Collector via OTLP/gRPC.
Each service calls `init_telemetry(service_name)` at startup.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

if TYPE_CHECKING:
    from opentelemetry.metrics import Meter
    from opentelemetry.trace import Tracer

logger = logging.getLogger(__name__)

# Default OTel Collector endpoint (inside Docker network)
DEFAULT_OTEL_ENDPOINT = "http://otel-collector:4317"


def init_telemetry(
    service_name: str,
    otel_endpoint: str = DEFAULT_OTEL_ENDPOINT,
) -> tuple[Meter, Tracer]:
    """Initialize OpenTelemetry metrics and tracing for a service.

    Returns (meter, tracer) for the service to create instruments.
    """
    resource = Resource.create({"service.name": service_name})

    # --- Tracing ---
    span_exporter = OTLPSpanExporter(endpoint=otel_endpoint, insecure=True)
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)
    tracer = trace.get_tracer(service_name)

    # --- Metrics ---
    metric_exporter = OTLPMetricExporter(endpoint=otel_endpoint, insecure=True)
    reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=10_000)
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(meter_provider)
    meter = metrics.get_meter(service_name)

    logger.info("OpenTelemetry initialized for %s → %s", service_name, otel_endpoint)
    return meter, tracer
