package vn.ttts.keygen;

import android.util.Base64;
import org.bouncycastle.crypto.params.Ed25519PrivateKeyParameters;
import org.bouncycastle.crypto.signers.Ed25519Signer;

import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.UUID;

public class KeyGeneratorCore {

    // Master Ed25519 Private Key Seed (Khớp 100% với T-TTS v3.0 Desktop)
    private static final String MASTER_SEED_HEX = "4a1b18652f0eac2a9acc7b65ab1ce72b1599e80ed21908010c73c65896acd72f";

    public static class LicenseResult {
        public final String keyString;
        public final String licenseId;
        public final String machineId;
        public final String planCode;
        public final String planName;
        public final long issuedAt;
        public final String issuedAtReadable;
        public final String note;

        public LicenseResult(String keyString, String licenseId, String machineId,
                             String planCode, String planName, long issuedAt,
                             String issuedAtReadable, String note) {
            this.keyString = keyString;
            this.licenseId = licenseId;
            this.machineId = machineId;
            this.planCode = planCode;
            this.planName = planName;
            this.issuedAt = issuedAt;
            this.issuedAtReadable = issuedAtReadable;
            this.note = note;
        }
    }

    public static LicenseResult createLicense(String machineId, String planKey, String note) throws Exception {
        String cleanMid = (machineId == null ? "" : machineId.trim().toUpperCase());
        if (cleanMid.isEmpty()) {
            throw new IllegalArgumentException("Mã máy (Machine ID) không được để trống.");
        }

        String planCode;
        String planName;
        Integer hours = null;
        Integer months = null;
        Boolean permanent = null;

        switch (planKey.toLowerCase(Locale.ROOT)) {
            case "1d":
                planCode = "KEY-1D";
                planName = "1 Ngày (24 giờ)";
                hours = 24;
                break;
            case "7d":
                planCode = "KEY-7D";
                planName = "7 Ngày (168 giờ)";
                hours = 168;
                break;
            case "30d":
                planCode = "KEY-30D";
                planName = "30 Ngày (720 giờ)";
                hours = 720;
                break;
            case "6m":
                planCode = "KEY-6M";
                planName = "6 Tháng (Theo lịch)";
                months = 6;
                break;
            case "1y":
                planCode = "KEY-1Y";
                planName = "1 Năm (Theo lịch)";
                break;
            case "perm":
                planCode = "KEY-PERM";
                planName = "Vĩnh viễn (Trọn đời)";
                permanent = true;
                break;
            default:
                throw new IllegalArgumentException("Gói bản quyền không hợp lệ: " + planKey);
        }

        long issuedAt = System.currentTimeMillis() / 1000L;
        String licId = UUID.randomUUID().toString();

        // TreeMap tự động sắp xếp các khóa theo thứ tự bảng chữ cái để tạo Canonical JSON chuẩn
        Map<String, Object> payloadMap = new TreeMap<>();
        payloadMap.put("v", 1);
        payloadMap.put("lid", licId);
        payloadMap.put("mid", cleanMid);
        payloadMap.put("plan", planCode);
        payloadMap.put("iat", issuedAt);

        if (hours != null) {
            payloadMap.put("hours", hours);
        }
        if (months != null) {
            payloadMap.put("months", months);
        }
        if (permanent != null && permanent) {
            payloadMap.put("permanent", true);
        }

        String cleanNote = (note == null ? "" : note.trim());
        if (!cleanNote.isEmpty()) {
            payloadMap.put("note", cleanNote);
        }

        // Chuyển sang JSON canonical
        String canonicalJson = toCanonicalJson(payloadMap);
        byte[] canonicalBytes = canonicalJson.getBytes(StandardCharsets.UTF_8);

        // Ký số Ed25519
        byte[] seedBytes = hexToBytes(MASTER_SEED_HEX);
        Ed25519PrivateKeyParameters privKey = new Ed25519PrivateKeyParameters(seedBytes, 0);
        Ed25519Signer signer = new Ed25519Signer();
        signer.init(true, privKey);
        signer.update(canonicalBytes, 0, canonicalBytes.length);
        byte[] signature = signer.generateSignature();

        // Base64 URL-safe không padding
        String payloadB64 = Base64.encodeToString(canonicalBytes, Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING);
        String sigB64 = Base64.encodeToString(signature, Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING);

        String keyString = "TTTS-LIC1-" + payloadB64 + "." + sigB64;

        SimpleDateFormat sdf = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault());
        String readableDate = sdf.format(new Date(issuedAt * 1000L));

        return new LicenseResult(keyString, licId, cleanMid, planCode, planName, issuedAt, readableDate, cleanNote);
    }

    private static String toCanonicalJson(Map<String, Object> map) {
        StringBuilder sb = new StringBuilder();
        sb.append("{");
        boolean first = true;
        for (Map.Entry<String, Object> entry : map.entrySet()) {
            if (!first) sb.append(",");
            first = false;
            sb.append("\"").append(entry.getKey()).append("\":");
            Object val = entry.getValue();
            if (val instanceof String) {
                sb.append("\"").append(escapeJson((String) val)).append("\"");
            } else if (val instanceof Number || val instanceof Boolean) {
                sb.append(val.toString());
            }
        }
        sb.append("}");
        return sb.toString();
    }

    private static String escapeJson(String s) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"': sb.append("\\\""); break;
                case '\\': sb.append("\\\\"); break;
                case '\b': sb.append("\\b"); break;
                case '\f': sb.append("\\f"); break;
                case '\n': sb.append("\\n"); break;
                case '\r': sb.append("\\r"); break;
                case '\t': sb.append("\\t"); break;
                default:
                    if (c < 32) {
                        sb.append(String.format(Locale.US, "\\u%04x", (int) c));
                    } else {
                        sb.append(c);
                    }
            }
        }
        return sb.toString();
    }

    private static byte[] hexToBytes(String s) {
        int len = s.length();
        byte[] data = new byte[len / 2];
        for (int i = 0; i < len; i += 2) {
            data[i / 2] = (byte) ((Character.digit(s.charAt(i), 16) << 4)
                    + Character.digit(s.charAt(i + 1), 16));
        }
        return data;
    }
}
