import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/spend_result.dart';
import '../models/user_balance.dart';
import 'api_exception.dart';

/// Low-level HTTP client for all EkoMatik backend requests.
///
/// This class intentionally knows HTTP details (URLs, headers, JSON encoding,
/// status-code handling), while the UI remains completely unaware of them.
/// The application can therefore replace the backend URL without changing
/// any screen code.
class ApiService {
  final String baseUrl;
  final String accessToken;
  final http.Client _client;

  /// Creates an API service.
  ///
  /// [baseUrl] should point to the FastAPI server, for example:
  /// `http://192.168.1.100:8000`.
  ///
  /// [accessToken] is the JWT Bearer token issued by the authentication layer.
  /// For the requested mock-auth setup, a test JWT can be supplied here.
  ApiService({
    required this.baseUrl,
    required this.accessToken,
    http.Client? client,
  }) : _client = client ?? http.Client();

  /// Builds common HTTP headers for JSON endpoints.
  ///
  /// The same JWT is attached to every mobile-app request that requires
  /// authentication.
  Map<String, String> get _authHeaders => {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': 'Bearer $accessToken',
      };

  /// Sends `POST /api/v1/cards/link` to attach an RFID card to the user.
  ///
  /// The backend uses the authenticated JWT to determine which user receives
  /// the card; therefore only the RFID UID is included in the request body.
  Future<void> linkCard(String rfidUid) async {
    final Uri uri = Uri.parse('$baseUrl/api/v1/cards/link');

    final http.Response response = await _client
        .post(
          uri,
          headers: _authHeaders,
          body: jsonEncode({'rfid_uid': rfidUid.trim()}),
        )
        .timeout(const Duration(seconds: 10));

    await _handleResponse(response);
  }

  /// Sends `POST /api/v1/transactions/spend` for donation or transfer.
  ///
  /// [amount] is the amount of EkoMatik balance to spend.
  /// [targetPartnerId] identifies the partner/organization receiving the
  /// donation or transfer.
  /// [transactionType] must match the backend enum, for example
  /// `DONATE_STK` or `TRANSFER_TRANSIT`.
  Future<SpendResult> spend({
    required double amount,
    required String targetPartnerId,
    required String transactionType,
  }) async {
    final Uri uri = Uri.parse('$baseUrl/api/v1/transactions/spend');

    final http.Response response = await _client
        .post(
          uri,
          headers: _authHeaders,
          body: jsonEncode({
            'amount': amount,
            'partner_id': targetPartnerId,
            'type': transactionType,
          }),
        )
        .timeout(const Duration(seconds: 10));

    final Map<String, dynamic> json = await _handleResponse(response);
    return SpendResult.fromJson(json);
  }

  /// Gets the user's current balance.
  ///
  /// This example expects a lightweight backend endpoint:
  /// `GET /api/v1/users/me` returning at minimum `{ "total_balance": 12.34 }`.
  /// If the current FastAPI project does not expose this route yet, this is the
  /// single backend endpoint that needs to be added for HomeView refresh.
  Future<UserBalance> getCurrentBalance() async {
    final Uri uri = Uri.parse('$baseUrl/api/v1/users/me');

    final http.Response response = await _client
        .get(uri, headers: _authHeaders)
        .timeout(const Duration(seconds: 10));

    final Map<String, dynamic> json = await _handleResponse(response);
    return UserBalance.fromJson(json);
  }

  /// Handles HTTP errors consistently for every endpoint.
  ///
  /// The backend's important application errors are mapped into human-readable
  /// messages. This means the widgets only need to display the exception in a
  /// Snackbar instead of duplicating HTTP status-code logic.
  Future<Map<String, dynamic>> _handleResponse(http.Response response) async {
    Map<String, dynamic> body = <String, dynamic>{};

    if (response.body.isNotEmpty) {
      try {
        final dynamic decoded = jsonDecode(response.body);
        if (decoded is Map<String, dynamic>) {
          body = decoded;
        }
      } catch (_) {
        // A non-JSON error body is allowed; the status-code mapping below will
        // still produce a useful message for the user.
      }
    }

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return body;
    }

    final String backendMessage =
        (body['detail'] ?? body['message'] ?? '').toString();

    throw ApiException(
      statusCode: response.statusCode,
      message: _messageForStatus(response.statusCode, backendMessage),
    );
  }

  /// Converts backend status codes into UI-friendly Turkish messages.
  ///
  /// The mapping deliberately keeps the raw backend message as a fallback so
  /// that new API error types can still be shown without a mobile release.
  String _messageForStatus(int statusCode, String backendMessage) {
    switch (statusCode) {
      case 400:
        return backendMessage.isNotEmpty
            ? backendMessage
            : 'Yetersiz bakiye veya geçersiz işlem.';
      case 401:
        return 'Oturum doğrulanamadı. Lütfen tekrar giriş yapın.';
      case 403:
        return 'Bu işlem için yetkiniz yok.';
      case 404:
        return 'İstenen kaynak bulunamadı.';
      case 409:
        return backendMessage.isNotEmpty
            ? backendMessage
            : 'Kart zaten başka bir kullanıcıya ekli.';
      case 422:
        return 'Gönderilen bilgiler geçerli değil.';
      case 500:
        return 'Sunucu hatası oluştu. Lütfen tekrar deneyin.';
      default:
        return backendMessage.isNotEmpty
            ? backendMessage
            : 'Beklenmeyen bir hata oluştu. Kod: $statusCode';
    }
  }

  /// Releases the underlying HTTP client when the application no longer uses
  /// the service. In a larger application this would normally be called from
  /// the application's dependency/lifecycle layer.
  void dispose() {
    _client.close();
  }
}