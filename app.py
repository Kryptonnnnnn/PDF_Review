from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
import pandas as pd
import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "supersecretkey_change_in_production"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def generate_user_id():
    """Generate unique user ID for session"""
    if "user_id" not in session:
        session["user_id"] = str(uuid.uuid4())
    return session["user_id"]


def get_user_folder():
    """Create and return user-specific folder"""
    user_id = generate_user_id()
    user_folder = os.path.join(UPLOAD_FOLDER, user_id)
    os.makedirs(user_folder, exist_ok=True)
    return user_folder


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        # Generate unique user ID
        user_id = generate_user_id()
        user_folder = get_user_folder()
        
        csv_file = request.files["csv_file"]
        filename = secure_filename(csv_file.filename)
        
        # Add timestamp to filename for uniqueness
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"{timestamp}_{filename}"
        path = os.path.join(user_folder, unique_filename)
        
        csv_file.save(path)

        df = pd.read_csv(path)

        # ✅ Remove duplicate links (keep first occurrence)
        if "link" in df.columns:
            original_count = len(df)
            df = df.drop_duplicates(subset=["link"])
            duplicates_removed = original_count - len(df)
            if duplicates_removed > 0:
                flash(f"ℹ️ Removed {duplicates_removed} duplicate link(s)")
        else:
            flash("⚠️ 'link' column not found in the CSV file.")
            return redirect(url_for("index"))

        # ✅ Add Status column if missing, fill empty values with empty string
        if "Status" not in df.columns:
            df["Status"] = ""
        else:
            df["Status"] = df["Status"].fillna("")

        # ✅ Save as reviewed copy
        reviewed_filename = f"{timestamp}_{filename.replace('.csv', '_reviewed.csv')}"
        reviewed_path = os.path.join(user_folder, reviewed_filename)
        df.to_csv(reviewed_path, index=False)

        # Store paths in session with user_id prefix
        session["csv_path"] = reviewed_path
        session["original_filename"] = filename
        session["index"] = 0
        session["total_docs"] = len(df)
        
        flash(f"✅ CSV uploaded successfully! {len(df)} unique links ready for review.")
        return redirect(url_for("viewer"))

    return render_template("index.html")


@app.route("/viewer", methods=["GET", "POST"])
def viewer():
    csv_path = session.get("csv_path")
    user_id = session.get("user_id")
    
    if not csv_path or not os.path.exists(csv_path):
        flash("⚠️ Please upload a CSV first.")
        return redirect(url_for("index"))

    # Verify the file belongs to this user
    if user_id and user_id not in csv_path:
        flash("⚠️ Invalid session. Please upload a new CSV.")
        return redirect(url_for("index"))

    df = pd.read_csv(csv_path)
    df["Status"] = df["Status"].fillna("")
    
    i = session.get("index", 0)

    # ✅ Handle navigation and status updates
    if request.method == "POST":
        action = request.form.get("action")

        if action in ["Accepted", "Rejected"]:
            df.loc[i, "Status"] = action
            df.to_csv(csv_path, index=False)
            flash(f"✅ Marked as {action}")
            
            # Auto-advance to next document
            if i < len(df) - 1:
                session["index"] = i + 1
                return redirect(url_for("viewer"))

        elif action == "Next":
            if i < len(df) - 1:
                session["index"] = i + 1

        elif action == "Previous":
            if i > 0:
                session["index"] = i - 1

        return redirect(url_for("viewer"))

    # ✅ When finished reviewing all PDFs
    if i >= len(df):
        return render_template("done.html")

    # ✅ Safely extract PDF link and status
    pdf_link = str(df.loc[i, "link"])
    name = os.path.basename(pdf_link)
    status = str(df.loc[i, "Status"]) if pd.notna(df.loc[i, "Status"]) and df.loc[i, "Status"] != "" else ""

    # Calculate statistics
    accepted_count = len(df[df["Status"] == "Accepted"])
    rejected_count = len(df[df["Status"] == "Rejected"])
    pending_count = len(df[df["Status"] == ""])

    return render_template(
        "viewer.html",
        pdf_link=pdf_link,
        index=i + 1,
        total=len(df),
        name=name,
        status=status,
        accepted_count=accepted_count,
        rejected_count=rejected_count,
        pending_count=pending_count
    )


@app.route("/view_sheet")
def view_sheet():
    csv_path = session.get("csv_path")
    user_id = session.get("user_id")
    
    if not csv_path or not os.path.exists(csv_path):
        flash("⚠️ No reviewed CSV available. Please upload and review first.")
        return redirect(url_for("index"))
    
    # Verify the file belongs to this user
    if user_id and user_id not in csv_path:
        flash("⚠️ Invalid session. Please upload a new CSV.")
        return redirect(url_for("index"))

    df = pd.read_csv(csv_path)
    df["Status"] = df["Status"].fillna("")

    # Convert DataFrame to HTML table for rendering
    table_html = df.to_html(classes="styled-table", index=False, escape=False)

    return render_template("sheet.html", table_html=table_html)


@app.route("/download_results")
def download_results():
    csv_path = session.get("csv_path")
    original_filename = session.get("original_filename", "reviewed.csv")
    user_id = session.get("user_id")
    
    if not csv_path or not os.path.exists(csv_path):
        flash("⚠️ No reviewed CSV available.")
        return redirect(url_for("index"))
    
    # Verify the file belongs to this user
    if user_id and user_id not in csv_path:
        flash("⚠️ Invalid session. Please upload a new CSV.")
        return redirect(url_for("index"))
    
    # Use original filename with _reviewed suffix
    download_name = original_filename.replace(".csv", "_reviewed.csv")
    return send_file(csv_path, as_attachment=True, download_name=download_name)


@app.route("/reset")
def reset():
    """Reset current session"""
    session.clear()
    flash("✅ Session reset successfully!")
    return redirect(url_for("index"))


@app.route("/cleanup")
def cleanup():
    """Clean up old user folders (optional - for maintenance)"""
    # This would typically be run as a scheduled task
    import time
    current_time = time.time()
    
    for user_folder in os.listdir(UPLOAD_FOLDER):
        folder_path = os.path.join(UPLOAD_FOLDER, user_folder)
        if os.path.isdir(folder_path):
            # Delete folders older than 24 hours
            folder_age = current_time - os.path.getmtime(folder_path)
            if folder_age > 86400:  # 24 hours in seconds
                try:
                    import shutil
                    shutil.rmtree(folder_path)
                except Exception as e:
                    print(f"Error deleting {folder_path}: {e}")
    
    return "Cleanup completed", 200


if __name__ == "__main__":
    app.run(debug=True, threaded=True)
