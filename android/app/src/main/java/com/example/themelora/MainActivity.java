package com.example.themelora;

import android.app.Activity;
import android.os.Bundle;
import android.widget.TextView;

public class MainActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        TextView view = new TextView(this);
        view.setText(getString(R.string.hello_themelora));
        view.setTextSize(24);
        setContentView(view);
    }
}
