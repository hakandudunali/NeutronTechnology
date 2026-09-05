import 'package:flutter/material.dart';

import 'repositories/ekomatik_repository.dart';
import 'services/api_service.dart';
import 'views/home_view.dart';

/// Application entry point.
void main() {
  // Replace these values with the real FastAPI host and the JWT returned by
  // your authentication layer. For a local Android emulator, an API running
  // on the development machine is commonly accessed through 10.0.2.2.
  const String backendBaseUrl = 'http://10.0.2.2:8000';
  const String mockJwt = 'REPLACE_WITH_MOCK_JWT';

  final ApiService apiService = ApiService(
    baseUrl: backendBaseUrl,
    accessToken: mockJwt,
  );

  final EkomatikRepository repository = EkomatikRepository(apiService);

  runApp(EkomatikApp(repository: repository));
}

/// Root Material application.
class EkomatikApp extends StatelessWidget {
  final EkomatikRepository repository;

  const EkomatikApp({super.key, required this.repository});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'EkoMatik',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.green),
        useMaterial3: true,
      ),
      home: HomeView(repository: repository),
    );
  }
}