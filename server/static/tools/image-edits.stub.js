/* ──────────────────────────────────────────────────────────────────────────
 * image-edits.stub.js — WP-7.5.1b — Capability slot stub
 *
 * STUB for the WP-7.3.3b `image_edits` capability slot. The real slot will
 * (a) accept a mask via the routing layer, (b) dispatch to a DALL-E 2 inpaint
 * model (or compatible Replicate host), (c) return a new image envelope
 * for the canvas. This stub is just enough to verify that the brush-mask
 * tool produces a payload `image_edits` can consume.
 *
 * Mask envelope shapes accepted (cross-WP coordination — see brush-mask.tool.js):
 *   • { kind: 'rect_mask',    parent_image_id, bbox: {x,y,w,h} }            (WP-7.5.1a)
 *   • { kind: 'raster_mask',  parent_image_id, parent_image_bbox, mask_data_url, mask_pixel_count, created_at } (WP-7.5.1b)
 *   • { kind: 'polygon_mask', parent_image_id, points: [[x,y],...] }         (WP-7.5.1c)
 *
 * Real slot will rasterize rect/polygon masks to PNG before dispatch; raster
 * masks pass through directly. This stub just validates the shape and
 * returns a synthetic ack envelope.
 *
 * ────────────────────────────────────────────────────────────────────── */

(function () {
  'use strict';

  /**
   * Validate a mask envelope. Returns { ok: bool, errors: [string] }.
   *
   * Validation rules per the cross-WP shape contract:
   *   - `kind` is one of the three discriminators
   *   - `parent_image_id` is a non-empty string (image_unreadable otherwise)
   *   - shape-specific required fields are present
   *   - raster_mask: data URL starts with 'data:image/png;base64,'
   *                  mask_pixel_count > 0
   */
  function validateMask(mask) {
    var errors = [];
    if (!mask || typeof mask !== 'object') {
      return { ok: false, errors: ['mask must be an object'] };
    }
    var validKinds = { rect_mask: true, raster_mask: true, polygon_mask: true };
    if (!validKinds[mask.kind]) {
      errors.push('unknown mask kind: ' + String(mask.kind));
    }
    if (!mask.parent_image_id || typeof mask.parent_image_id !== 'string') {
      errors.push('missing parent_image_id (image_unreadable)');
    }

    if (mask.kind === 'raster_mask') {
      if (!mask.mask_data_url || typeof mask.mask_data_url !== 'string') {
        errors.push('raster_mask requires mask_data_url');
      } else if (mask.mask_data_url.indexOf('data:image/png;base64,') !== 0) {
        errors.push('raster_mask mask_data_url must be PNG data URL');
      }
      if (!(mask.mask_pixel_count > 0)) {
        errors.push('raster_mask must have mask_pixel_count > 0');
      }
      if (!mask.parent_image_bbox || typeof mask.parent_image_bbox !== 'object') {
        errors.push('raster_mask requires parent_image_bbox');
      } else {
        var b = mask.parent_image_bbox;
        if (!(b.width > 0) || !(b.height > 0)) {
          errors.push('parent_image_bbox must have positive width and height');
        }
      }
    }

    if (mask.kind === 'rect_mask') {
      if (!mask.bbox || typeof mask.bbox !== 'object') {
        errors.push('rect_mask requires bbox');
      }
    }

    if (mask.kind === 'polygon_mask') {
      if (!Array.isArray(mask.points) || mask.points.length < 3) {
        errors.push('polygon_mask requires points array (>= 3 points)');
      }
    }

    return { ok: errors.length === 0, errors: errors };
  }

  /**
   * Stub dispatch. Real version will route to a model and return an image
   * envelope; this returns a synthetic ack the test harness can inspect.
   */
  function imageEdits(opts) {
    opts = opts || {};
    var v = validateMask(opts.mask);
    if (!v.ok) {
      return {
        ok:     false,
        error:  'invalid_mask',
        errors: v.errors
      };
    }
    return {
      ok:                  true,
      stubbed:             true,
      received_mask_kind:  opts.mask.kind,
      received_image_id:   opts.mask.parent_image_id,
      received_prompt:     opts.prompt || null,
      received_mask_bytes: (opts.mask.mask_data_url || '').length
    };
  }

  if (typeof window !== 'undefined') {
    window.OraCapabilityStubs = window.OraCapabilityStubs || {};
    window.OraCapabilityStubs.image_edits = imageEdits;
    window.OraCapabilityStubs.validateMask = validateMask;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { imageEdits: imageEdits, validateMask: validateMask };
  }
})();
