CREATE TABLE `artwork_series` (
	`id` text PRIMARY KEY NOT NULL,
	`title` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `series_members` (
	`artwork_id` text PRIMARY KEY NOT NULL,
	`series_id` text NOT NULL,
	`position` integer NOT NULL,
	FOREIGN KEY (`series_id`) REFERENCES `artwork_series`(`id`) ON UPDATE no action ON DELETE no action
);

--> statement-breakpoint
INSERT INTO artwork_series (id,title) VALUES ('turquoise-coral','Turquoise and Coral Brushstrokes');
--> statement-breakpoint
INSERT INTO series_members (artwork_id,series_id,position) VALUES ('art-013','turquoise-coral',0);
--> statement-breakpoint
INSERT INTO series_members (artwork_id,series_id,position) VALUES ('art-008','turquoise-coral',1);
--> statement-breakpoint
INSERT INTO artwork_series (id,title) VALUES ('monochrome-figures','Monochrome figures');
--> statement-breakpoint
INSERT INTO series_members (artwork_id,series_id,position) VALUES ('art-069','monochrome-figures',0);
--> statement-breakpoint
INSERT INTO series_members (artwork_id,series_id,position) VALUES ('art-080','monochrome-figures',1);
--> statement-breakpoint
INSERT INTO artwork_series (id,title) VALUES ('turquoise-miniatures','Turquoise brushstrokes');
--> statement-breakpoint
INSERT INTO series_members (artwork_id,series_id,position) VALUES ('art-009','turquoise-miniatures',0);
--> statement-breakpoint
INSERT INTO series_members (artwork_id,series_id,position) VALUES ('art-010','turquoise-miniatures',1);
--> statement-breakpoint
INSERT INTO series_members (artwork_id,series_id,position) VALUES ('art-011','turquoise-miniatures',2);
--> statement-breakpoint
INSERT INTO series_members (artwork_id,series_id,position) VALUES ('art-012','turquoise-miniatures',3);
--> statement-breakpoint
CREATE TRIGGER sync_series_order_insert AFTER INSERT ON artwork_edits
WHEN json_type(NEW.document,'$.order') = 'integer'
BEGIN
  INSERT INTO artwork_edits (artwork_id,document,revision,updated_at,updated_by)
  SELECT companion.artwork_id,json_object('order',json_extract(NEW.document,'$.order')),1,NEW.updated_at,NEW.updated_by
  FROM series_members AS current JOIN series_members AS companion ON companion.series_id=current.series_id
  WHERE current.artwork_id=NEW.artwork_id AND companion.artwork_id<>NEW.artwork_id
  ON CONFLICT(artwork_id) DO UPDATE SET
    document=json_set(artwork_edits.document,'$.order',json_extract(NEW.document,'$.order')),
    revision=artwork_edits.revision+1,updated_at=NEW.updated_at,updated_by=NEW.updated_by
  WHERE json_extract(artwork_edits.document,'$.order') IS NOT json_extract(NEW.document,'$.order');
END;
--> statement-breakpoint
CREATE TRIGGER sync_series_order_update AFTER UPDATE ON artwork_edits
WHEN json_type(NEW.document,'$.order') = 'integer'
BEGIN
  INSERT INTO artwork_edits (artwork_id,document,revision,updated_at,updated_by)
  SELECT companion.artwork_id,json_object('order',json_extract(NEW.document,'$.order')),1,NEW.updated_at,NEW.updated_by
  FROM series_members AS current JOIN series_members AS companion ON companion.series_id=current.series_id
  WHERE current.artwork_id=NEW.artwork_id AND companion.artwork_id<>NEW.artwork_id
  ON CONFLICT(artwork_id) DO UPDATE SET
    document=json_set(artwork_edits.document,'$.order',json_extract(NEW.document,'$.order')),
    revision=artwork_edits.revision+1,updated_at=NEW.updated_at,updated_by=NEW.updated_by
  WHERE json_extract(artwork_edits.document,'$.order') IS NOT json_extract(NEW.document,'$.order');
END;
--> statement-breakpoint
