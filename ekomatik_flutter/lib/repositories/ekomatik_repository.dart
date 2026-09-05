import '../models/spend_result.dart';
import '../models/user_balance.dart';
import '../services/api_service.dart';

/// Repository layer between Flutter widgets and the low-level API service.
///
/// The repository hides transport details from the UI and gives future features
/// one stable place to add caching, local storage, retry logic, analytics, or
/// offline synchronization without rewriting the screens.
class EkomatikRepository {
  final ApiService apiService;

  const EkomatikRepository(this.apiService);

  /// Loads the currently authenticated user's balance from the backend.
  Future<UserBalance> getBalance() => apiService.getCurrentBalance();

  /// Links a new RFID card to the currently authenticated user.
  Future<void> linkCard(String rfidUid) => apiService.linkCard(rfidUid);

  /// Creates a donation/transfer spending transaction.
  Future<SpendResult> spend({
    required double amount,
    required String targetPartnerId,
    required String transactionType,
  }) {
    return apiService.spend(
      amount: amount,
      targetPartnerId: targetPartnerId,
      transactionType: transactionType,
    );
  }
}