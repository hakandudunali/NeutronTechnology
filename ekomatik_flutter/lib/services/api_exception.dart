/// A typed exception used by the API service so that the UI does not need to
/// understand raw HTTP response bodies or status codes.
class ApiException implements Exception {
  final int statusCode;
  final String message;

  const ApiException({required this.statusCode, required this.message});

  @override
  String toString() => 'ApiException($statusCode): $message';
}