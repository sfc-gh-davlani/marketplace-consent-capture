"""
Marketplace Listing — Explicit Terms & Conditions Acceptance Capture
----------------------------------------------------------------------
Public version for Streamlit Community Cloud. No Snowflake login
required by the consumer — connects to Snowflake via a dedicated
service account (key-pair auth) to write the acceptance record.
"""

import streamlit as st
import snowflake.connector

TABLE = "MARKETPLACE_E2E.PUBLIC.TERMS_ACCEPTANCE_LOG"
TERMS_VERSION = "v1.0 - 2026-09-14"
TERMS_URL = "https://example-provider.com/legal/terms-of-service"

SAMPLE_TERMS_TEXT = """
**Freddie Mac Data Product — Listing Terms of Service**

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
production use.)*
"""


@st.cache_resource
def get_connection():
    return snowflake.connector.connect(
        user=st.secrets["snowflake"]["user"],
        account=st.secrets["snowflake"]["account"],
        private_key_file=None,
        private_key=st.secrets["snowflake"]["private_key"].encode(),
        role=st.secrets["snowflake"].get("role", "CONSENT_APP_ROLE"),
        warehouse=st.secrets["snowflake"].get("warehouse", "TEMP"),
    )


st.set_page_config(page_title="Listing Terms Acceptance", layout="centered")

st.title("Data Product Access Request")
st.caption("Freddie Mac — Single Family Loan Deal Dataset · Limited Trial Follow-up")

st.markdown(
    "Before we provision full access to this data product, please review "
    "and explicitly accept the Terms & Conditions below."
)

st.divider()
st.subheader("Terms & Conditions")
st.caption(f"Version: {TERMS_VERSION}  ·  [View full terms]({TERMS_URL})")

with st.container(border=True):
    st.markdown(SAMPLE_TERMS_TEXT)

st.divider()
st.subheader("Your Information")

col1, col2 = st.columns(2)
with col1:
    consumer_name = st.text_input("Full Name*", placeholder="Jane Smith")
with col2:
    consumer_company = st.text_input("Company*", placeholder="Acme Inc.")

consumer_email = st.text_input("Business Email*", placeholder="jane.smith@acme.com")
listing_name = st.text_input(
    "Listing Name", value="Single Family Loan Deal Dataset", disabled=True
)

st.divider()
agree = st.checkbox("**I have read and agree to the Terms & Conditions above.**")
submitted = st.button("Accept & Submit", type="primary", disabled=not agree)

if submitted:
    missing = []
    if not consumer_name.strip():
        missing.append("Full Name")
    if not consumer_company.strip():
        missing.append("Company")
    if not consumer_email.strip() or "@" not in consumer_email:
        missing.append("a valid Business Email")

    if missing:
        st.error(f"Please provide: {', '.join(missing)}.")
    else:
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                f"""
                INSERT INTO {TABLE}
                    (LISTING_NAME, CONSUMER_NAME, CONSUMER_EMAIL,
                     CONSUMER_COMPANY, TERMS_VERSION, TERMS_URL, ACCEPTED)
                SELECT %s, %s, %s, %s, %s, %s, TRUE
                """,
                (
                    listing_name,
                    consumer_name.strip(),
                    consumer_email.strip(),
                    consumer_company.strip(),
                    TERMS_VERSION,
                    TERMS_URL,
                ),
            )
            cur.close()
            st.success(
                "Your acceptance has been recorded. Our team will now "
                "provision your private listing and notify you by email."
            )
        except Exception as e:
            st.error(f"Something went wrong submitting your acceptance: {e}")
