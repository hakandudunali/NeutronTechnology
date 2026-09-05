/// Represents the authenticated user's current EkoMatik balance.
///
/// The backend can return additional user fields later. Keeping this response
/// model small makes the UI independent from the full Users database table.
class UserBalance {
  final double balance;

  const UserBalance({required this.balance});

  /// Creates a [UserBalance] from a JSON response.
  ///
  /// We accept both `total_balance` (database-oriented naming) and `balance`
  /// (UI-oriented naming) to make the Flutter client tolerant of either API
  /// response shape.
  factory UserBalance.fromJson(Map<String, dynamic> json) {
    final dynamic raw = json['total_balance'] ?? json['balance'];

    if (raw == null) {
      throw const FormatException('Balance field is missing.');
    }

    return UserBalance(balance: double.parse(raw.toString()));
  }
}