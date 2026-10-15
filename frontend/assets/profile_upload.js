// /profile pictures: every picture picked with the pencil buttons is converted to WebP in the browser BEFORE it is
// uploaded (resized to at most 1600 px on its longest side, then re-encoded smaller until it is under ~900 KB), so
// a 6 MB phone photo travels as a few hundred KB and passes nginx's default 1 MB body limit. The server converts
// again (profile_service) and is the real check; if the browser cannot convert a file the original goes up unchanged.
(function () {
  if (window.__profileUploadWebp) return;
  window.__profileUploadWebp = true;
  var MAX_SIDE = 1600;
  var TARGET_BYTES = 900 * 1024;
  var done = new WeakSet(); // inputs whose files were just replaced: let that change event through

  function toBlob(canvas, quality) {
    return new Promise(function (resolve) { canvas.toBlob(resolve, "image/webp", quality); });
  }

  async function convert(file) {
    var bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
    var scale = Math.min(1, MAX_SIDE / Math.max(bmp.width, bmp.height));
    var best = null;
    for (var round = 0; round < 4; round++) {
      var canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(bmp.width * scale));
      canvas.height = Math.max(1, Math.round(bmp.height * scale));
      canvas.getContext("2d").drawImage(bmp, 0, 0, canvas.width, canvas.height);
      var qualities = [0.85, 0.75, 0.6];
      for (var i = 0; i < qualities.length; i++) {
        var blob = await toBlob(canvas, qualities[i]);
        if (!blob || blob.type !== "image/webp") throw new Error("webp not supported");
        best = blob;
        if (blob.size <= TARGET_BYTES) { bmp.close && bmp.close(); return blob; }
      }
      scale *= 0.75;
    }
    bmp.close && bmp.close();
    return best;
  }

  document.addEventListener(
    "change",
    function (e) {
      var input = e.target;
      if (!input || input.type !== "file" || !input.closest || !input.closest(".profile-upload")) return;
      if (done.has(input)) { done.delete(input); return; }
      var file = input.files && input.files[0];
      if (!file || !/^image\//.test(file.type) || file.type === "image/svg+xml") return;
      e.stopImmediatePropagation(); // the upload starts from the converted file below
      convert(file)
        .then(function (blob) {
          var name = (file.name || "picture").replace(/\.[^.]+$/, "") + ".webp";
          return new File([blob], name, { type: "image/webp" });
        })
        .catch(function () { return file; }) // not convertible here: send the original, the server decides
        .then(function (out) {
          var dt = new DataTransfer();
          dt.items.add(out);
          input.files = dt.files;
          done.add(input);
          input.dispatchEvent(new Event("change", { bubbles: true }));
        });
    },
    true
  );
})();
