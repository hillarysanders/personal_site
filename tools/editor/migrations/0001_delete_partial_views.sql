-- Remove saved overrides for the three discarded background fragments.
DELETE FROM artwork_edits WHERE artwork_id IN ('art-083', 'art-084', 'art-085');
