from app.models.user import User


def test_user_model_has_expected_columns():
    columns = {c.name for c in User.__table__.columns}
    assert columns == {
        "id", "email", "password_hash", "github_id", "github_username",
        "github_access_token_encrypted", "avatar_url", "plan", "created_at", "updated_at",
    }
