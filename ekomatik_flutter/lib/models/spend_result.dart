/// Represents a successful spending/donation transaction response.
///
/// Field names mirror the backend's `SpendResponse` schema exactly
/// (see ekomatik_backend/app/schemas/schemas.py -> SpendResponse):
/// `status`, `transaction_id`, `user_id`, `new_balance`.
class SpendResult {
  final String status;
  final String transactionId;
  final double newBalance;

  const SpendResult({
    required this.status,
    required this.transactionId,
    required this.newBalance,
  });

  /// Converts the backend JSON response into a strongly typed Dart object.
  factory SpendResult.fromJson(Map<String, dynamic> json) {
    final dynamic rawBalance = json['new_balance'];

    if (rawBalance == null) {
      throw const FormatException('new_balance field is missing.');
    }

    return SpendResult(
      status: (json['status'] ?? 'success').toString(),
      transactionId: (json['transaction_id'] ?? '').toString(),
      newBalance: double.parse(rawBalance.toString()),
    );
  }
}
