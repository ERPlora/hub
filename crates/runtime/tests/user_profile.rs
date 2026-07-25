use erplora_db::testutil::fresh_db;
use erplora_runtime::user_profile::{UpdateUserProfile, UserPreferences};
use erplora_runtime::Runtime;

async fn runtime(hub_id: &str) -> Runtime {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt
}

#[tokio::test]
async fn preferences_are_per_user_and_none_means_inherit() {
    let rt = runtime("hub-a").await;
    let alice = rt
        .create_user("Alice Doe", "1111", "admin", None)
        .await
        .unwrap();
    let bob = rt
        .create_user("Bob Roe", "2222", "employee", None)
        .await
        .unwrap();

    let initial = rt.user_profile(&alice).await.unwrap();
    assert_eq!(initial.first_name, "Alice");
    assert_eq!(initial.preferences, UserPreferences::default());

    rt.update_user_profile(
        &alice,
        &UpdateUserProfile {
            first_name: "Alicia".into(),
            last_name: "Doe".into(),
            email: "alice@example.com".into(),
            preferences: UserPreferences {
                language: Some("en".into()),
                theme_mode: Some("dark".into()),
                theme_palette: Some("ocean".into()),
            },
        },
    )
    .await
    .unwrap();

    let alice_profile = rt.user_profile(&alice).await.unwrap();
    assert_eq!(alice_profile.name, "Alicia Doe");
    assert_eq!(alice_profile.preferences.language.as_deref(), Some("en"));
    assert_eq!(
        alice_profile.preferences.theme_palette.as_deref(),
        Some("ocean")
    );

    let bob_profile = rt.user_profile(&bob).await.unwrap();
    assert_eq!(bob_profile.preferences, UserPreferences::default());

    let reset = rt
        .update_user_profile(
            &alice,
            &UpdateUserProfile {
                first_name: "Alicia".into(),
                last_name: "Doe".into(),
                email: "alice@example.com".into(),
                preferences: UserPreferences::default(),
            },
        )
        .await
        .unwrap();
    assert_eq!(reset.preferences, UserPreferences::default());
}

#[tokio::test]
async fn invalid_preferences_are_rejected() {
    let rt = runtime("hub-a").await;
    let user = rt.create_user("User", "", "employee", None).await.unwrap();
    let err = rt
        .update_user_profile(
            &user,
            &UpdateUserProfile {
                first_name: "User".into(),
                last_name: String::new(),
                email: String::new(),
                preferences: UserPreferences {
                    language: Some("fr".into()),
                    ..UserPreferences::default()
                },
            },
        )
        .await
        .unwrap_err();
    assert!(err.to_string().contains("language"));
}
