CREATE TABLE `artwork_edits` (
	`artwork_id` text PRIMARY KEY NOT NULL,
	`document` text NOT NULL,
	`revision` integer NOT NULL,
	`updated_at` text NOT NULL,
	`updated_by` text NOT NULL
);
