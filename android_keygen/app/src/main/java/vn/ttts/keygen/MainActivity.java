package vn.ttts.keygen;

import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.RadioGroup;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

public class MainActivity extends AppCompatActivity {

    private EditText etMachineId;
    private EditText etNote;
    private RadioGroup rgPlans;
    private View layoutResult;
    private TextView tvKeyResult;
    private TextView tvSummaryInfo;

    private String lastGeneratedKey = "";
    private KeyGeneratorCore.LicenseResult lastResult = null;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        etMachineId = findViewById(R.id.etMachineId);
        etNote = findViewById(R.id.etNote);
        rgPlans = findViewById(R.id.rgPlans);
        layoutResult = findViewById(R.id.layoutResult);
        tvKeyResult = findViewById(R.id.tvKeyResult);
        tvSummaryInfo = findViewById(R.id.tvSummaryInfo);

        Button btnPaste = findViewById(R.id.btnPaste);
        Button btnUniversal = findViewById(R.id.btnUniversal);
        Button btnGenerate = findViewById(R.id.btnGenerate);
        Button btnCopyKey = findViewById(R.id.btnCopyKey);
        Button btnShareKey = findViewById(R.id.btnShareKey);

        // Nút Dán từ Clipboard
        btnPaste.setOnClickListener(v -> {
            ClipboardManager clipboard = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
            if (clipboard != null && clipboard.hasPrimaryClip() && clipboard.getPrimaryClip() != null) {
                ClipData.Item item = clipboard.getPrimaryClip().getItemAt(0);
                if (item != null && item.getText() != null) {
                    String pasted = item.getText().toString().trim();
                    etMachineId.setText(pasted);
                    etMachineId.setSelection(pasted.length());
                    Toast.makeText(this, "Đã dán mã máy!", Toast.LENGTH_SHORT).show();
                    return;
                }
            }
            Toast.makeText(this, "Bộ nhớ tạm không có dữ liệu!", Toast.LENGTH_SHORT).show();
        });

        // Nút Key Dùng Chung (Universal)
        btnUniversal.setOnClickListener(v -> {
            etMachineId.setText("*");
            etMachineId.setSelection(1);
            Toast.makeText(this, "Đã chọn mã dùng chung cho mọi máy (*)", Toast.LENGTH_SHORT).show();
        });

        // Nút Tạo Key
        btnGenerate.setOnClickListener(v -> generateKey());

        // Nút Sao Chép Key
        btnCopyKey.setOnClickListener(v -> {
            if (!lastGeneratedKey.isEmpty()) {
                ClipboardManager clipboard = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                ClipData clip = ClipData.newPlainText("T-TTS License Key", lastGeneratedKey);
                if (clipboard != null) {
                    clipboard.setPrimaryClip(clip);
                    Toast.makeText(this, "Đã sao chép mã bản quyền vào bộ nhớ tạm!", Toast.LENGTH_SHORT).show();
                }
            }
        });

        // Nút Chia sẻ qua Zalo/Tin nhắn
        btnShareKey.setOnClickListener(v -> {
            if (lastResult != null) {
                String shareText = "Kính gửi quý khách,\n\n"
                        + "Mã bản quyền phần mềm T-TTS v3.0 của bạn:\n"
                        + "----------------------------------------\n"
                        + lastResult.keyString + "\n"
                        + "----------------------------------------\n"
                        + "• Mã máy: " + lastResult.machineId + "\n"
                        + "• Gói bản quyền: " + lastResult.planName + "\n"
                        + "• Ngày phát hành: " + lastResult.issuedAtReadable + "\n"
                        + (lastResult.note.isEmpty() ? "" : "• Ghi chú: " + lastResult.note + "\n")
                        + "• Tác giả: Nguyễn Văn Tiệp\n\n"
                        + "Hướng dẫn: Quý khách mở phần mềm T-TTS v3.0, vào mục Bản quyền, dán mã trên vào và bấm Kích hoạt.";

                Intent sendIntent = new Intent(Intent.ACTION_SEND);
                sendIntent.putExtra(Intent.EXTRA_TEXT, shareText);
                sendIntent.setType("text/plain");

                Intent shareChooser = Intent.createChooser(sendIntent, "Gửi mã bản quyền qua...");
                startActivity(shareChooser);
            }
        });
    }

    private void generateKey() {
        String machineId = etMachineId.getText().toString().trim();
        if (machineId.isEmpty()) {
            Toast.makeText(this, "Vui lòng nhập Mã máy (Machine ID)!", Toast.LENGTH_LONG).show();
            etMachineId.requestFocus();
            return;
        }

        String planKey = "1y";
        int checkedId = rgPlans.getCheckedRadioButtonId();
        if (checkedId == R.id.rb1D) {
            planKey = "1d";
        } else if (checkedId == R.id.rb7D) {
            planKey = "7d";
        } else if (checkedId == R.id.rb30D) {
            planKey = "30d";
        } else if (checkedId == R.id.rb6M) {
            planKey = "6m";
        } else if (checkedId == R.id.rb1Y) {
            planKey = "1y";
        } else if (checkedId == R.id.rbPerm) {
            planKey = "perm";
        }

        String note = etNote.getText().toString().trim();

        try {
            lastResult = KeyGeneratorCore.createLicense(machineId, planKey, note);
            lastGeneratedKey = lastResult.keyString;

            tvKeyResult.setText(lastGeneratedKey);
            String summary = "Gói: " + lastResult.planName
                    + " | Máy: " + lastResult.machineId
                    + "\nCấp lúc: " + lastResult.issuedAtReadable
                    + (lastResult.note.isEmpty() ? "" : " | " + lastResult.note);
            tvSummaryInfo.setText(summary);

            layoutResult.setVisibility(View.VISIBLE);
            Toast.makeText(this, "✅ Đã tạo mã bản quyền thành công!", Toast.LENGTH_SHORT).show();
        } catch (Exception e) {
            Toast.makeText(this, "Lỗi tạo key: " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }
}
