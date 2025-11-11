from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
import pandas as pd
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "supersecretkey"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        csv_file = request.files["csv_file"]
        filename = secure_filename(csv_file.filename)
        path = os.path.join(UPLOAD_FOLDER, filename)
        csv_file.save(path)

        df = pd.read_csv(path)

        # ✅ Remove duplicate links (keep first occurrence)
        if "link" in df.columns:
            df = df.drop_duplicates(subset=["link"])
        else:
            flash("⚠️ 'link' column not found in the CSV file.")
            return redirect(url_for("index"))

        # ✅ Add Status column if missing
        if "Status" not in df.columns:
            df["Status"] = ""

        # ✅ Save as reviewed copy to keep original safe
        reviewed_path = path.replace(".csv", "_reviewed.csv")
        df.to_csv(reviewed_path, index=False)

        session["csv_path"] = reviewed_path
        session["index"] = 0
        flash(f"✅ CSV uploaded successfully! {len(df)} unique links ready for review.")
        return redirect(url_for("viewer"))

    return render_template("index.html")


@app.route("/viewer", methods=["GET", "POST"])
def viewer():
    csv_path = session.get("csv_path")
    if not csv_path or not os.path.exists(csv_path):
        flash("⚠️ Please upload a CSV first.")
        return redirect(url_for("index"))

    df = pd.read_csv(csv_path)
    i = session.get("index", 0)

    # ✅ Handle navigation and status updates
    if request.method == "POST":
        action = request.form.get("action")

        if action in ["Accepted", "Rejected"]:
            df.loc[i, "Status"] = action
            df.to_csv(csv_path, index=False)
            flash(f"✅ Marked as {action}")

        elif action == "Next":
            if i < len(df) - 1:
                session["index"] = i + 1

        elif action == "Previous":
            if i > 0:
                session["index"] = i - 1

        elif action == "CheckStatus":
            # Just reload the current CSV to show the updated status
            flash("🔄 Status refreshed from the latest CSV file.")

        return redirect(url_for("viewer"))

    # ✅ When finished reviewing all PDFs
    if i >= len(df):
        return render_template("done.html")

    # ✅ Safely extract PDF link
    pdf_link = str(df.loc[i, "link"])
    name = os.path.basename(pdf_link)
    status = df.loc[i, "Status"]

    return render_template(
        "viewer.html",
        pdf_link=pdf_link,
        index=i + 1,
        total=len(df),
        name=name,
        status=status
    )


@app.route("/download_results")
def download_results():
    csv_path = session.get("csv_path")
    if csv_path and os.path.exists(csv_path):
        return send_file(csv_path, as_attachment=True)
    flash("⚠️ No reviewed CSV available.")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
