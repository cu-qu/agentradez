from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.permissions import HasTradingAccess
from execution.models import ExecutionAccount, ExecutionAgentToken, ExecutionOAuthClient, HarnessJournal, HarnessPosition, HarnessSignal
from execution.serializers import (
    CoinbaseConnectSerializer,
    ExecutionAccountCreateSerializer,
    ExecutionAccountSerializer,
    ExecutionAccountUpdateSerializer,
    ExecutionAgentTokenCreateSerializer,
    ExecutionAgentTokenSerializer,
    HarnessJournalSerializer,
    HarnessPositionSerializer,
    HarnessSignalSerializer,
    KalshiConnectSerializer,
)
from trading.models import BrokerConnection
from trading.constants import BROKER_COINBASE, BROKER_KALSHI
from trading.services.credentials import encrypt_credentials


TRADING = [IsAuthenticated, HasTradingAccess]


class ExecutionAccountListCreateView(generics.ListCreateAPIView):
    permission_classes = TRADING
    serializer_class = ExecutionAccountSerializer
    pagination_class = None

    def get_queryset(self):
        return ExecutionAccount.objects.filter(user=self.request.user).select_related("broker_connection")

    @extend_schema(tags=["Execution"], summary="Create execution account")
    def post(self, request, *args, **kwargs):
        ser = ExecutionAccountCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        conn = get_object_or_404(
            BrokerConnection,
            pk=ser.validated_data["broker_connection_id"],
            user=request.user,
            is_deleted=False,
        )
        if ExecutionAccount.objects.filter(user=request.user, slug=ser.validated_data["slug"]).exists():
            return Response({"slug": "Already exists."}, status=status.HTTP_400_BAD_REQUEST)
        account = ExecutionAccount.objects.create(
            user=request.user,
            slug=ser.validated_data["slug"],
            label=ser.validated_data["label"],
            broker_connection=conn,
        )
        return Response(ExecutionAccountSerializer(account).data, status=status.HTTP_201_CREATED)


class ExecutionAccountDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = TRADING
    serializer_class = ExecutionAccountUpdateSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return ExecutionAccount.objects.filter(user=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        account = self.get_object()
        return Response(ExecutionAccountSerializer(account).data)


class ExecutionAgentTokenListCreateView(generics.ListCreateAPIView):
    permission_classes = TRADING
    pagination_class = None

    def get_queryset(self):
        return ExecutionAgentToken.objects.filter(user=self.request.user, revoked_at__isnull=True)

    def get_serializer_class(self):
        return ExecutionAgentTokenCreateSerializer if self.request.method == "POST" else ExecutionAgentTokenSerializer

    def create(self, request, *args, **kwargs):
        ser = ExecutionAgentTokenCreateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        row = ser.save()
        return Response(
            {
                "token": ser.context["raw_token"],
                "agent_token": ExecutionAgentTokenSerializer(row).data,
                "mcp_url": f"{request.build_absolute_uri('/').rstrip('/')}/api/mcp/execution/",
            },
            status=status.HTTP_201_CREATED,
        )


class ExecutionAgentTokenRevokeView(APIView):
    permission_classes = TRADING

    def post(self, request, pk):
        row = get_object_or_404(ExecutionAgentToken, pk=pk, user=request.user)
        from django.utils import timezone

        row.revoked_at = timezone.now()
        row.save(update_fields=["revoked_at"])
        return Response({"status": "revoked"})


class KalshiConnectView(APIView):
    permission_classes = TRADING

    def post(self, request):
        ser = KalshiConnectSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        creds = {
            "kalshi_api_key_id": data["api_key_id"],
            "kalshi_private_key_pem": data["private_key_pem"],
            "kalshi_api_base_url": data.get("kalshi_api_base_url") or "",
            "kalshi_use_demo": data.get("kalshi_use_demo", True),
        }
        conn = _upsert_broker(request.user, BROKER_KALSHI, creds)
        account, _ = ExecutionAccount.objects.get_or_create(
            user=request.user,
            slug=data["slug"],
            defaults={"label": data["label"], "broker_connection": conn},
        )
        if account.broker_connection_id != conn.id:
            account.broker_connection = conn
            account.save(update_fields=["broker_connection", "updated_at"])
        return Response(
            {"broker_connection_id": conn.id, "execution_account": ExecutionAccountSerializer(account).data},
            status=status.HTTP_201_CREATED,
        )


class CoinbaseConnectView(APIView):
    permission_classes = TRADING

    def post(self, request):
        ser = CoinbaseConnectSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        creds = {
            "coinbase_api_key_name": data["api_key_name"],
            "coinbase_private_key_pem": data["private_key_pem"],
            "coinbase_api_base_url": data.get("coinbase_api_base_url") or "",
        }
        conn = _upsert_broker(request.user, BROKER_COINBASE, creds)
        account, _ = ExecutionAccount.objects.get_or_create(
            user=request.user,
            slug=data["slug"],
            defaults={"label": data["label"], "broker_connection": conn},
        )
        if account.broker_connection_id != conn.id:
            account.broker_connection = conn
            account.save(update_fields=["broker_connection", "updated_at"])
        return Response(
            {"broker_connection_id": conn.id, "execution_account": ExecutionAccountSerializer(account).data},
            status=status.HTTP_201_CREATED,
        )


def _upsert_broker(user, broker: str, creds: dict) -> BrokerConnection:
    from decimal import Decimal

    conn = BrokerConnection.objects.filter(user=user, broker=broker, is_deleted=False).first()
    if conn is None:
        conn = BrokerConnection.objects.create(
            user=user,
            broker=broker,
            encrypted_credentials=encrypt_credentials(creds),
            status=BrokerConnection.Status.CONNECTED,
            last_equity=Decimal("0"),
        )
    else:
        conn.encrypted_credentials = encrypt_credentials(creds)
        conn.status = BrokerConnection.Status.CONNECTED
        conn.save(update_fields=["encrypted_credentials", "status", "updated_at"])
    return conn


class HarnessSignalListView(generics.ListAPIView):
    permission_classes = TRADING
    serializer_class = HarnessSignalSerializer
    pagination_class = None

    def get_queryset(self):
        return HarnessSignal.objects.filter(user=self.request.user).select_related("execution_account")[:200]


class HarnessPositionListView(generics.ListAPIView):
    permission_classes = TRADING
    serializer_class = HarnessPositionSerializer
    pagination_class = None

    def get_queryset(self):
        return HarnessPosition.objects.filter(user=self.request.user).select_related("signal")[:200]


class HarnessJournalListView(generics.ListAPIView):
    permission_classes = TRADING
    serializer_class = HarnessJournalSerializer
    pagination_class = None

    def get_queryset(self):
        return HarnessJournal.objects.filter(user=self.request.user).select_related("signal")[:200]
