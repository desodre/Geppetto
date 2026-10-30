package com.example.geppettologindemo;

import android.app.Activity;
import android.os.Bundle;
import android.text.InputType;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

/** A deterministic login form for the Geppetto pytest example; it uses no network or accounts. */
public class MainActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        LinearLayout form = new LinearLayout(this);
        form.setOrientation(LinearLayout.VERTICAL);
        int padding = (int) (24 * getResources().getDisplayMetrics().density);
        form.setPadding(padding, padding, padding, padding);

        EditText username = new EditText(this);
        username.setId(R.id.username);
        username.setHint("Username");
        username.setSingleLine(true);
        form.addView(username);

        EditText password = new EditText(this);
        password.setId(R.id.password);
        password.setHint("Password");
        password.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        form.addView(password);

        TextView result = new TextView(this);
        result.setId(R.id.login_result);
        result.setText("Sign in");

        Button login = new Button(this);
        login.setId(R.id.login_button);
        login.setText("Log in");
        login.setOnClickListener((View view) -> {
            boolean valid = username.getText().toString().equals("demo")
                    && password.getText().toString().equals("geppetto");
            result.setText(valid ? "Welcome, demo!" : "Invalid credentials");
        });
        form.addView(login);
        form.addView(result);

        setContentView(form);
    }
}
