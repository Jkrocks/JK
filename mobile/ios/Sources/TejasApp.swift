import CryptoKit
import SwiftUI
import UIKit
import WebKit

/// Tejas AI for iPhone and iPad.
///
/// Tejas's brain runs on the family's home computer. This app finds it on the
/// home Wi-Fi, pairs with it (the family checks a short code), and from then on
/// only trusts that computer's own "Tejas Home CA" certificate.
@main
struct TejasAIApp: App {
    var body: some Scene {
        WindowGroup {
            WebContainer()
                .ignoresSafeArea()
                .background(Color(red: 0.02, green: 0.043, blue: 0.043))
                .preferredColorScheme(.dark)
        }
    }
}

struct WebContainer: UIViewControllerRepresentable {
    func makeUIViewController(context: Context) -> TejasViewController { TejasViewController() }
    func updateUIViewController(_ vc: TejasViewController, context: Context) {}
}

/// Avoids a retain cycle between WKUserContentController and the view controller.
final class WeakHandler: NSObject, WKScriptMessageHandler {
    weak var target: WKScriptMessageHandler?
    init(_ target: WKScriptMessageHandler) { self.target = target }
    func userContentController(_ c: WKUserContentController, didReceive m: WKScriptMessage) {
        target?.userContentController(c, didReceive: m)
    }
}

final class TejasViewController: UIViewController, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler {
    private var web: WKWebView!
    private let store = UserDefaults.standard
    private var pendingCA: [String: Data] = [:]

    // MARK: Life cycle
    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = UIColor(red: 0.02, green: 0.043, blue: 0.043, alpha: 1)
        let config = WKWebViewConfiguration()
        config.allowsInlineMediaPlayback = true
        config.mediaTypesRequiringUserActionForPlayback = []
        let ucc = WKUserContentController()
        ucc.add(WeakHandler(self), name: "tejas")
        // Same shape as the Android bridge, so the Tejas web app can offer "pair with another computer".
        let shim = """
        window.TejasApp = window.TejasApp || {
          scan: () => webkit.messageHandlers.tejas.postMessage({cmd: "scan", arg: ""}),
          probe: (u) => webkit.messageHandlers.tejas.postMessage({cmd: "probe", arg: u}),
          trust: (u) => webkit.messageHandlers.tejas.postMessage({cmd: "trust", arg: u}),
          forget: () => webkit.messageHandlers.tejas.postMessage({cmd: "forget", arg: ""}),
          platform: () => "ios"
        };
        """
        ucc.addUserScript(WKUserScript(source: shim, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        config.userContentController = ucc
        web = WKWebView(frame: view.bounds, configuration: config)
        web.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        web.isOpaque = false
        web.backgroundColor = view.backgroundColor
        web.scrollView.backgroundColor = view.backgroundColor
        web.navigationDelegate = self
        web.uiDelegate = self
        view.addSubview(web)

        if let saved = store.string(forKey: "url"), let url = URL(string: saved) {
            web.load(URLRequest(url: url))
        } else {
            showConnect(nil)
        }
    }

    override var preferredStatusBarStyle: UIStatusBarStyle { .lightContent }

    private func showConnect(_ message: String?) {
        guard let file = Bundle.main.url(forResource: "connect", withExtension: "html") else { return }
        var target = file
        if let m = message, let enc = m.addingPercentEncoding(withAllowedCharacters: .alphanumerics) {
            target = URL(string: file.absoluteString + "#" + enc) ?? file
        }
        web.loadFileURL(target, allowingReadAccessTo: file.deletingLastPathComponent())
    }

    private func js(_ fn: String, _ obj: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: obj),
              let json = String(data: data, encoding: .utf8) else { return }
        DispatchQueue.main.async { self.web.evaluateJavaScript("window.\(fn) && window.\(fn)(\(json))") }
    }

    // MARK: Certificates
    private var trustedCAs: [SecCertificate] {
        let list = store.array(forKey: "cas") as? [Data] ?? []
        return list.compactMap { SecCertificateCreateWithData(nil, $0 as CFData) }
    }

    private func shortCode(_ der: Data) -> String {
        let hex = SHA256.hash(data: der).map { String(format: "%02X", $0) }.joined()
        let head = Array(hex.prefix(16))
        return stride(from: 0, to: 16, by: 4).map { String(head[$0..<$0 + 4]) }.joined(separator: " ")
    }

    private func normalise(_ input: String) -> URL? {
        var s = input.trimmingCharacters(in: .whitespacesAndNewlines)
        while s.hasSuffix("/") { s.removeLast() }
        if !s.hasPrefix("http") { s = "https://" + s }
        s = s.replacingOccurrences(of: "http://", with: "https://")
        guard var c = URLComponents(string: s), c.host != nil else { return nil }
        if c.port == nil { c.port = 8443 }
        c.path = ""
        return c.url
    }

    // MARK: Messages from connect.html
    func userContentController(_ c: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any], let cmd = body["cmd"] as? String else { return }
        let arg = body["arg"] as? String ?? ""
        switch cmd {
        case "scan": scan()
        case "probe": probe(arg)
        case "trust": trust(arg)
        case "forget":
            store.removeObject(forKey: "url")
            showConnect(nil)
        default: break
        }
    }

    private func probe(_ input: String) {
        guard let base = normalise(input) else {
            js("onProbe", ["ok": false, "url": input, "error": "That doesn't look like an address."])
            return
        }
        Prober.status(base, timeout: 5) { [weak self] json, chain in
            guard let self = self else { return }
            guard let json = json, let ca = chain.last else {
                self.js("onProbe", ["ok": false, "url": base.absoluteString,
                                    "error": "Couldn't reach Tejas there. Check the address and that the home computer is on."])
                return
            }
            let der = SecCertificateCopyData(ca) as Data
            DispatchQueue.main.async {
                self.pendingCA[base.absoluteString] = der
                self.js("onProbe", ["ok": true, "url": base.absoluteString,
                                    "name": json["name"] as? String ?? "Tejas", "code": self.shortCode(der)])
            }
        }
    }

    private func trust(_ urlString: String) {
        guard let der = pendingCA[urlString], let url = URL(string: urlString) else { return }
        var list = store.array(forKey: "cas") as? [Data] ?? []
        if !list.contains(der) { list.append(der) }
        store.set(list, forKey: "cas")
        store.set(urlString, forKey: "url")
        web.load(URLRequest(url: url))
    }

    private func scan() {
        let prefixes = Network.lanPrefixes()
        if prefixes.isEmpty {
            js("onScanDone", ["error": "This device isn't on a home Wi-Fi network."])
            return
        }
        let targets = prefixes.flatMap { p in (1...254).map { "\(p).\($0)" } }
        let group = DispatchGroup()
        let limit = DispatchSemaphore(value: 48)
        DispatchQueue.global(qos: .userInitiated).async {
            for ip in targets {
                limit.wait()
                group.enter()
                let base = URL(string: "https://\(ip):8443")!
                Prober.status(base, timeout: 1.2) { [weak self] json, _ in
                    if let json = json {
                        self?.js("onFound", ["url": base.absoluteString, "name": json["name"] as? String ?? "Tejas"])
                    }
                    limit.signal()
                    group.leave()
                }
            }
            group.notify(queue: .main) { [weak self] in self?.js("onScanDone", [:]) }
        }
    }

    // MARK: Web view
    func webView(_ webView: WKWebView, didReceive challenge: URLAuthenticationChallenge,
                 completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
              let trust = challenge.protectionSpace.serverTrust else {
            completionHandler(.performDefaultHandling, nil)
            return
        }
        let anchors = trustedCAs
        guard !anchors.isEmpty else {
            completionHandler(.cancelAuthenticationChallenge, nil)
            return
        }
        // Trust only certificates made by a paired Tejas Home CA.
        SecTrustSetPolicies(trust, SecPolicyCreateBasicX509())
        SecTrustSetAnchorCertificates(trust, anchors as CFArray)
        SecTrustSetAnchorCertificatesOnly(trust, true)
        var error: CFError?
        if SecTrustEvaluateWithError(trust, &error) {
            completionHandler(.useCredential, URLCredential(trust: trust))
        } else {
            completionHandler(.cancelAuthenticationChallenge, nil)
        }
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        let host = URL(string: store.string(forKey: "url") ?? "")?.host ?? "the home computer"
        showConnect("Can't reach Tejas at \(host). Is the home computer on and Tejas running? If you set Tejas up again, pair again.")
    }

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url else { return decisionHandler(.allow) }
        let home = URL(string: store.string(forKey: "url") ?? "")
        if url.isFileURL || url.scheme == "about" || (url.host == home?.host && url.port == home?.port) {
            decisionHandler(.allow)
        } else {
            UIApplication.shared.open(url)
            decisionHandler(.cancel)
        }
    }

    @available(iOS 15.0, *)
    func webView(_ webView: WKWebView, requestMediaCapturePermissionFor origin: WKSecurityOrigin,
                 initiatedByFrame frame: WKFrameInfo, type: WKMediaCaptureType,
                 decisionHandler: @escaping (WKPermissionDecision) -> Void) {
        let home = URL(string: store.string(forKey: "url") ?? "")
        decisionHandler(origin.host == home?.host && type == .microphone ? .grant : .deny)
    }
}

/// Reads /api/status from a candidate Tejas computer and notes its certificate chain.
/// Used only to find and pair; the app content itself is checked against the pinned CA.
final class Prober: NSObject, URLSessionDelegate {
    private var chain: [SecCertificate] = []

    static func status(_ base: URL, timeout: TimeInterval, done: @escaping ([String: Any]?, [SecCertificate]) -> Void) {
        let p = Prober()
        let cfg = URLSessionConfiguration.ephemeral
        cfg.timeoutIntervalForRequest = timeout
        cfg.timeoutIntervalForResource = timeout * 3
        let session = URLSession(configuration: cfg, delegate: p, delegateQueue: nil)
        session.dataTask(with: base.appendingPathComponent("api/status")) { data, _, _ in
            var json: [String: Any]?
            if let d = data, let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any], j["version"] != nil {
                json = j
            }
            done(json, p.chain)
            session.finishTasksAndInvalidate()
        }.resume()
    }

    func urlSession(_ session: URLSession, didReceive challenge: URLAuthenticationChallenge,
                    completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        guard let trust = challenge.protectionSpace.serverTrust else {
            completionHandler(.performDefaultHandling, nil)
            return
        }
        chain = (SecTrustCopyCertificateChain(trust) as? [SecCertificate]) ?? []
        completionHandler(.useCredential, URLCredential(trust: trust))
    }
}

enum Network {
    /// "192.168.1" style prefixes for this device's private IPv4 addresses.
    static func lanPrefixes() -> [String] {
        var out = Set<String>()
        var ifaddr: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&ifaddr) == 0, let first = ifaddr else { return [] }
        defer { freeifaddrs(ifaddr) }
        for ptr in sequence(first: first, next: { $0.pointee.ifa_next }) {
            guard let sa = ptr.pointee.ifa_addr, sa.pointee.sa_family == UInt8(AF_INET) else { continue }
            var host = [CChar](repeating: 0, count: Int(NI_MAXHOST))
            getnameinfo(sa, socklen_t(sa.pointee.sa_len), &host, socklen_t(host.count), nil, 0, NI_NUMERICHOST)
            let ip = String(cString: host)
            let parts = ip.split(separator: ".").compactMap { Int($0) }
            guard parts.count == 4 else { continue }
            let isPrivate = parts[0] == 10 || (parts[0] == 192 && parts[1] == 168) || (parts[0] == 172 && (16...31).contains(parts[1]))
            if isPrivate { out.insert(parts.prefix(3).map(String.init).joined(separator: ".")) }
        }
        return Array(out)
    }
}
