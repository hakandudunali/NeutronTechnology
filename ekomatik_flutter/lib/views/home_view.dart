import 'package:flutter/material.dart';

import '../repositories/ekomatik_repository.dart';
import '../services/api_exception.dart';
import '../widgets/balance_card.dart';

/// Main application screen for EkoMatik users.
///
/// Riverpod/Provider is intentionally not used here. A simple StatefulWidget
/// owns the UI state so that the project remains easy to understand while the
/// Service/Repository architecture keeps HTTP logic out of the widget.
class HomeView extends StatefulWidget {
  final EkomatikRepository repository;

  const HomeView({super.key, required this.repository});

  @override
  State<HomeView> createState() => _HomeViewState();
}

class _HomeViewState extends State<HomeView> {
  double _balance = 0.0;
  bool _isLoadingBalance = false;
  bool _isLinkingCard = false;
  bool _isSpending = false;

  @override
  void initState() {
    super.initState();
    _loadBalance();
  }

  /// Fetches the current balance and refreshes only this screen's state.
  Future<void> _loadBalance() async {
    setState(() => _isLoadingBalance = true);

    try {
      final result = await widget.repository.getBalance();
      if (!mounted) return;
      setState(() => _balance = result.balance);
    } catch (error) {
      if (!mounted) return;
      _showError(error);
    } finally {
      if (mounted) {
        setState(() => _isLoadingBalance = false);
      }
    }
  }

  /// Opens the RFID input dialog.
  ///
  /// Keeping the dialog as a dedicated method makes the main `build()` method
  /// easier to scan and makes it simple to replace the text field later with a
  /// QR scanner or NFC/RFID companion flow.
  Future<void> _showAddCardDialog() async {
    final TextEditingController controller = TextEditingController();

    await showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Kart Ekle'),
          content: TextField(
            controller: controller,
            autofocus: true,
            textCapitalization: TextCapitalization.characters,
            decoration: const InputDecoration(
              labelText: 'RFID UID',
              hintText: 'A1B2C3D4',
              border: OutlineInputBorder(),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text('İptal'),
            ),
            FilledButton(
              onPressed: () async {
                final String uid = controller.text.trim();

                if (uid.isEmpty) {
                  _showSnackBar('RFID kodunu giriniz.', isError: true);
                  return;
                }

                Navigator.of(dialogContext).pop();
                await _linkCard(uid);
              },
              child: const Text('Ekle'),
            ),
          ],
        );
      },
    );

    controller.dispose();
  }

  /// Sends the RFID UID to the repository and reports API errors as a Snackbar.
  Future<void> _linkCard(String uid) async {
    setState(() => _isLinkingCard = true);

    try {
      await widget.repository.linkCard(uid);
      if (!mounted) return;
      _showSnackBar('Kart başarıyla eklendi.');
    } catch (error) {
      if (!mounted) return;
      _showError(error);
    } finally {
      if (mounted) {
        setState(() => _isLinkingCard = false);
      }
    }
  }

  /// Shows the donation amount dialog and starts a TEMA donation request.
  Future<void> _showDonationDialog() async {
    final TextEditingController amountController = TextEditingController();

    await showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('TEMA\'ya Bağış Yap'),
          content: TextField(
            controller: amountController,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(
              labelText: 'Bağış miktarı',
              suffixText: 'Puan',
              border: OutlineInputBorder(),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text('İptal'),
            ),
            FilledButton(
              onPressed: () async {
                final double? amount = double.tryParse(
                  amountController.text.replaceAll(',', '.').trim(),
                );

                if (amount == null || amount <= 0) {
                  _showSnackBar(
                    'Geçerli bir bağış miktarı giriniz.',
                    isError: true,
                  );
                  return;
                }

                Navigator.of(dialogContext).pop();
                await _donateToTema(amount);
              },
              child: const Text('Bağış Yap'),
            ),
          ],
        );
      },
    );

    amountController.dispose();
  }

  /// Calls the spending endpoint using the backend transaction enum.
  ///
  /// `DONATE_STK` identifies the donation operation and `TEMA` is the partner
  /// identifier. The backend is still responsible for checking available
  /// balance and performing the atomic debit/log operation.
  Future<void> _donateToTema(double amount) async {
    setState(() => _isSpending = true);

    try {
      final result = await widget.repository.spend(
        amount: amount,
        targetPartnerId: 'TEMA',
        transactionType: 'DONATE_STK',
      );

      if (!mounted) return;

      // The backend's SpendResponse always includes the authoritative new
      // balance, so we can apply it directly without an extra GET request.
      setState(() => _balance = result.newBalance);

      if (!mounted) return;
      _showSnackBar('${amount.toStringAsFixed(2)} puan TEMA\'ya bağışlandı.');
    } catch (error) {
      if (!mounted) return;
      _showError(error);
    } finally {
      if (mounted) {
        setState(() => _isSpending = false);
      }
    }
  }

  /// Displays a consistent Snackbar for API or local application errors.
  void _showError(Object error) {
    if (error is ApiException) {
      _showSnackBar(
        '${error.message} (HTTP ${error.statusCode})',
        isError: true,
      );
      return;
    }

    _showSnackBar('Bir hata oluştu: $error', isError: true);
  }

  /// Displays a temporary feedback message at the bottom of the screen.
  void _showSnackBar(String message, {bool isError = false}) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(message),
          behavior: SnackBarBehavior.floating,
        ),
      );
  }

  @override
  Widget build(BuildContext context) {
    final bool busy = _isLoadingBalance || _isLinkingCard || _isSpending;

    return Scaffold(
      appBar: AppBar(
        title: const Text('EkoMatik'),
        actions: [
          IconButton(
            tooltip: 'Bakiyeyi yenile',
            onPressed: busy ? null : _loadBalance,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _loadBalance,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          children: [
            BalanceCard(balance: _balance),
            const SizedBox(height: 20),
            FilledButton.icon(
              onPressed: busy ? null : _showAddCardDialog,
              icon: const Icon(Icons.contactless),
              label: Text(_isLinkingCard ? 'Kart Ekleniyor...' : 'Kart Ekle'),
            ),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: busy ? null : _showDonationDialog,
              icon: const Icon(Icons.volunteer_activism),
              label: Text(
                _isSpending ? 'Bağış Gönderiliyor...' : 'TEMA\'ya Bağış Yap',
              ),
            ),
            const SizedBox(height: 24),
            const Card(
              child: Padding(
                padding: EdgeInsets.all(16),
                child: Text(
                  'EkoMatik cihazında attığınız her izmarit geri dönüşüme '
                  'katkı sağlar ve hesabınıza puan kazandırır.',
                ),
              ),
            ),
            if (_isLoadingBalance)
              const Padding(
                padding: EdgeInsets.only(top: 20),
                child: Center(child: CircularProgressIndicator()),
              ),
          ],
        ),
      ),
    );
  }
}