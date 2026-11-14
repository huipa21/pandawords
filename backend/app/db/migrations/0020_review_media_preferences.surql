DEFINE FIELD IF NOT EXISTS prefs.review_images_enabled ON user TYPE bool DEFAULT true;
DEFINE FIELD IF NOT EXISTS prefs.review_audio_enabled ON user TYPE bool DEFAULT true;
UPDATE user SET
    prefs.review_images_enabled = IF prefs.review_images_enabled = NONE THEN true ELSE prefs.review_images_enabled END,
    prefs.review_audio_enabled = IF prefs.review_audio_enabled = NONE THEN true ELSE prefs.review_audio_enabled END
WHERE prefs.review_images_enabled = NONE OR prefs.review_audio_enabled = NONE;
