def build_wait_check_params(keyword, date_text=""):
    params = {"keyword": str(keyword or "").strip()}
    selected_date = str(date_text or "").strip()
    if selected_date:
        params["date"] = selected_date
    return params
