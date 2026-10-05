@staticmethod
def _get_notebook_context_auth():
    """
    Return (workspace_url, short-lived context token) when running
    inside a Databricks workspace.

    Tries the Databricks runtime dbutils context directly first,
    then falls back to IPython only if necessary.
    """
    try:
        dbutils = None

        # ------------------------------------------------------------
        # 1. Try Databricks runtime-provided dbutils
        # ------------------------------------------------------------
        try:
            from dbruntime import dbutils as runtime_dbutils

            dbutils = runtime_dbutils
        except Exception:
            dbutils = None

        # ------------------------------------------------------------
        # 2. Fallback: obtain dbutils from the current IPython shell
        # ------------------------------------------------------------
        if dbutils is None:
            try:
                from IPython import get_ipython

                shell = get_ipython()

                if shell is not None:
                    dbutils = shell.user_ns.get("dbutils")
            except Exception:
                dbutils = None

        if dbutils is None:
            return None

        # ------------------------------------------------------------
        # 3. Read the current Databricks notebook execution context
        # ------------------------------------------------------------
        context = (
            dbutils.notebook
            .entry_point
            .getDbutils()
            .notebook()
            .getContext()
        )

        api_url = None
        api_token = None

        try:
            api_url_value = context.apiUrl()

            if api_url_value.isDefined():
                api_url = api_url_value.get()
        except Exception:
            pass

        try:
            api_token_value = context.apiToken()

            if api_token_value.isDefined():
                api_token = api_token_value.get()
        except Exception:
            pass

        # ------------------------------------------------------------
        # 4. Return runtime credentials if available
        # ------------------------------------------------------------
        if api_url and api_token:
            return str(api_url), str(api_token)

    except Exception as exc:
        logger.debug(
            "Databricks notebook context authentication unavailable: %s",
            exc,
        )

    return None
