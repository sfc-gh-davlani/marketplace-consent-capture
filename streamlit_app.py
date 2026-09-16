"""
Marketplace Listing -- Explicit Terms & Conditions Acceptance Capture
----------------------------------------------------------------------
Public version for Streamlit Community Cloud. No Snowflake login
required by the consumer -- connects to Snowflake via a dedicated
service account (key-pair auth) to write the acceptance record.

v2: Token-validated, terms-hashed, IP/UA-captured.
"""

import hashlib
import streamlit as st
import snowflake.connector
import base64

TABLE = "MARKETPLACE_E2E.PUBLIC.TERMS_ACCEPTANCE_LOG"
TOKEN_TABLE = "MARKETPLACE_E2E.PUBLIC.CONSENT_TOKENS"
REQUEST_TABLE = "MARKETPLACE_E2E.PUBLIC.LISTING_REQUESTS"
TERMS_VERSION = "v1.0 - 2026-09-14"
TERMS_URL = "https://example-provider.com/legal/terms-of-service"

SAMPLE_TERMS_TEXT = """\
**Freddie Mac Data Product -- Listing Terms of Service**

1. **Grant of Access.** Freddie Mac ("Provider") grants Consumer a limited,
   non-exclusive, non-transferable right to access and query the data
   product attached to this listing, solely for Consumer's internal
   business purposes.

2. **Restrictions.** Consumer shall not redistribute, resell, or
   sublicense the data product to any third party without Provider's
   prior written consent.

3. **No Warranty.** The data product is provided "as is" without
   warranties of any kind, express or implied.

4. **Term & Termination.** This agreement remains in effect until
   terminated by either party with 30 days' written notice.

5. **Governing Law.** Governed by the laws of the State of Virginia.

6. **Confidentiality.** Consumer agrees to maintain the confidentiality
   of any non-public data elements included in the data product.

*(Sample/demo terms text. Replace with actual legal terms before
production use.)*"""

# Pre-compute the SHA-256 hash of the terms text shown to every visitor
TERMS_HASH = hashlib.sha256(SAMPLE_TERMS_TEXT.encode("utf-8")).hexdigest()


@st.cache_resource
def get_connection():
    key_der = base64.b64decode(st.secrets["snowflake"]["private_key_b64"])
    return snowflake.connector.connect(
        user=st.secrets["snowflake"]["user"],
        account=st.secrets["snowflake"]["account"],
        private_key=key_der,
        role=st.secrets["snowflake"].get("role", "CONSENT_APP_ROLE"),
        warehouse=st.secrets["snowflake"].get("warehouse", "TEMP"),
    )


def validate_token(token: str) -> dict | None:
    """Return token row if valid (exists, not expired, not used), else None."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT ct.TOKEN_ID, ct.REQUEST_ID, ct.CONSUMER_EMAIL, ct.EXPIRES_AT, ct.USED,
               lr.LISTING_NAME, lr.CONSUMER_NAME, lr.CONSUMER_COMPANY
        FROM {TOKEN_TABLE} ct
        JOIN {REQUEST_TABLE} lr ON ct.REQUEST_ID = lr.REQUEST_ID
        WHERE ct.TOKEN = %s
        LIMIT 1
        """,
        (token,),
    )
    row = cur.fetchone()
    cur.close()
    if row is None:
        return None
    cols = ["TOKEN_ID", "REQUEST_ID", "CONSUMER_EMAIL", "EXPIRES_AT", "USED",
            "LISTING_NAME", "CONSUMER_NAME", "CONSUMER_COMPANY"]
    return dict(zip(cols, row))


def mark_token_used(token: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE {TOKEN_TABLE} SET USED = TRUE, USED_AT = CURRENT_TIMESTAMP() WHERE TOKEN = %s",
        (token,),
    )
    cur.close()


def get_client_ip() -> str:
    try:
        headers = st.context.headers
        forwarded = headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return headers.get("X-Real-Ip", "unknown")
    except Exception:
        return "unknown"


def get_user_agent() -> str:
    try:
        return st.context.headers.get("User-Agent", "unknown")
    except Exception:
        return "unknown"


# ---- Page config ----
st.set_page_config(page_title="Listing Terms Acceptance", layout="centered")

# ---- Token validation gate ----
token = st.query_params.get("token", "")

if not token:
    st.title("Data Product Access Request")
    st.warning(
        "This form requires a valid consent link sent to your email. "
        "If you requested access to a Freddie Mac data product, check your email "
        "for a message containing your unique consent link."
    )
    st.stop()

token_info = validate_token(token)

if token_info is None:
    st.title("Invalid Link")
    st.error("This consent link is not recognized. It may have been entered incorrectly.")
    st.stop()

if token_info["USED"]:
    st.title("Link Already Used")
    st.info(
        "This consent link has already been used to submit an acceptance. "
        "If you believe this is an error, please contact the data provider."
    )
    st.stop()

import datetime
if token_info["EXPIRES_AT"].replace(tzinfo=None) < datetime.datetime.utcnow():
    st.title("Link Expired")
    st.warning(
        "This consent link has expired. Please contact the data provider to request a new one."
    )
    st.stop()

# ---- Token is valid: render the consent form ----
listing_name = token_info["LISTING_NAME"]
consumer_name = token_info["CONSUMER_NAME"]
consumer_email = token_info["CONSUMER_EMAIL"]
consumer_company = token_info["CONSUMER_COMPANY"]

st.title("Data Product Access Request")
st.caption(f"Freddie Mac -- {listing_name} -- Explicit Consent Required")

st.markdown(
    "Before we provision full access to this data product, please review "
    "and explicitly accept the Terms & Conditions below."
)

st.divider()
st.subheader("Terms & Conditions")
st.caption(f"Version: {TERMS_VERSION}  |  [View full terms]({TERMS_URL})  |  Hash: `{TERMS_HASH[:16]}...`")

with st.container(border=True):
    st.markdown(SAMPLE_TERMS_TEXT)

st.divider()
st.subheader("Your Information")
st.markdown(f"**Name:** {consumer_name}  \n**Company:** {consumer_company}  \n**Email:** {consumer_email}")
st.caption("These details were pre-filled from your access request and cannot be changed.")

st.divider()
agree = st.checkbox("**I have read and agree to the Terms & Conditions above.**")
submitted = st.button("Accept & Submit", type="primary", disabled=not agree)

if submitted:
    client_ip = get_client_ip()
    user_agent = get_user_agent()

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            f"""
            INSERT INTO {TABLE}
                (LISTING_NAME, CONSUMER_NAME, CONSUMER_EMAIL,
                 CONSUMER_COMPANY, TERMS_VERSION, TERMS_URL, ACCEPTED,
                 CLIENT_IP, TERMS_HASH, USER_AGENT, CONSENT_TOKEN)
            SELECT %s, %s, %s, %s, %s, %s, TRUE, %s, %s, %s, %s
            """,
            (
                listing_name,
                consumer_name,
                consumer_email,
                consumer_company,
                TERMS_VERSION,
                TERMS_URL,
                client_ip,
                TERMS_HASH,
                user_agent,
                token,
            ),
        )
        cur.close()

        # Mark the token as used so it cannot be reused
        mark_token_used(token)

        st.success(
            "Your acceptance has been recorded. Our team will now "
            "provision your private listing and notify you by email."
        )
        st.balloons()
    except Exception as e:
        st.error(f"Something went wrong submitting your acceptance: {e}")
