import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

/// Error API — pesan saka backend (detail) ditampilke langsung.
class ApiException implements Exception {
  final int statusCode;
  final String message;

  ApiException(this.statusCode, this.message);

  @override
  String toString() => message;
}

class ApiClient {
  final String baseUrl;
  String? token;

  ApiClient(this.baseUrl);

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

  Uri _uri(String path, [Map<String, String>? query]) {
    final u = Uri.parse('$baseUrl$path');
    return (query != null && query.isNotEmpty) ? u.replace(queryParameters: query) : u;
  }

  Future<dynamic> post(String path, Map<String, dynamic> body) async {
    final res = await http
        .post(_uri(path), headers: _headers, body: jsonEncode(body))
        .timeout(const Duration(seconds: 20));
    return _decode(res);
  }

  Future<dynamic> put(String path, Map<String, dynamic> body) async {
    final res = await http
        .put(_uri(path), headers: _headers, body: jsonEncode(body))
        .timeout(const Duration(seconds: 20));
    return _decode(res);
  }

  Future<dynamic> patch(String path, Map<String, dynamic> body) async {
    final res = await http
        .patch(_uri(path), headers: _headers, body: jsonEncode(body))
        .timeout(const Duration(seconds: 20));
    return _decode(res);
  }

  Future<dynamic> delete(String path, {Map<String, dynamic>? body}) async {
    final res = await http
        .delete(_uri(path), headers: _headers,
            body: body == null ? null : jsonEncode(body))
        .timeout(const Duration(seconds: 20));
    return _decode(res);
  }

  Future<dynamic> get(String path, [Map<String, String>? query]) async {
    final res = await http.get(_uri(path, query), headers: _headers)
        .timeout(const Duration(seconds: 20));
    return _decode(res);
  }

  /// GET mentah (byte) — kanggo gambar QR PNG.
  Future<Uint8List> getBytes(String path) async {
    final res = await http.get(_uri(path), headers: _headers)
        .timeout(const Duration(seconds: 20));
    if (res.statusCode >= 200 && res.statusCode < 300) return res.bodyBytes;
    throw ApiException(res.statusCode, 'Error ${res.statusCode}');
  }

  /// Upload file (multipart) — kanggo import CSV.
  Future<dynamic> postMultipart(
    String path,
    List<int> bytes, {
    required String filename,
    Map<String, String>? fields,
  }) async {
    final req = http.MultipartRequest('POST', _uri(path));
    if (token != null) req.headers['Authorization'] = 'Bearer $token';
    if (fields != null) req.fields.addAll(fields);
    req.files.add(http.MultipartFile.fromBytes('file', bytes, filename: filename));
    final streamed = await req.send().timeout(const Duration(seconds: 60));
    final res = await http.Response.fromStream(streamed);
    return _decode(res);
  }

  dynamic _decode(http.Response res) {
    dynamic body;
    try {
      body = jsonDecode(res.body);
    } catch (_) {
      body = null;
    }
    if (res.statusCode >= 200 && res.statusCode < 300) return body;
    final msg = (body is Map && body['detail'] != null)
        ? body['detail'].toString()
        : 'Error ${res.statusCode}';
    throw ApiException(res.statusCode, msg);
  }
}
