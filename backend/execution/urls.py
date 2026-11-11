from django.urls import path

from execution.mcp_server import ExecutionMcpView

urlpatterns = [
    path("mcp/execution/", ExecutionMcpView.as_view(), name="execution-mcp"),
]
