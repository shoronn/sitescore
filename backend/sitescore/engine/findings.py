"""Plain-language wording for every finding.

Edit the text here, not in the checks. Placeholders like {days_left} come from the
check's evidence; a missing placeholder renders as "?".

offer: which MAKTECH offer fixes it
  none            nothing to sell, all good
  fixit           Fix-It Starter Pack (onboarding offer)
  cloudcare       CloudCare Managed Hosting (core offer)
  email_setup     Business Email & Deliverability (one-time offer 1)
  security_shield Security Shield + Email Tracker (one-time offer 2)
"""
from __future__ import annotations

from typing import Any

W = dict  # short alias for readability below

FINDINGS: dict[str, dict[str, dict[str, str]]] = {
    # ------------------------------------------------ AI agent readiness (scored separately)
    "robots_txt": {
        "ok": W(title="robots.txt is in place",
                summary="Your site publishes a valid robots.txt file.",
                why="It is the first file search engines and AI agents read to learn what they may visit.",
                fix="Nothing to do.", offer="none"),
        "invalid": W(title="robots.txt is not readable",
                     summary="/robots.txt answers, but not with valid robots rules.",
                     why="Search engines and AI agents ignore it, so they get no guidance about your site.",
                     fix="We publish a proper robots.txt with your sitemap and AI rules.", offer="fixit"),
        "missing": W(title="No robots.txt",
                     summary="Your site has no /robots.txt file.",
                     why="It is the first file search engines and AI agents look for. Without it they get no guidance about your site.",
                     fix="We publish a robots.txt with your sitemap and AI rules.", offer="fixit"),
    },
    "sitemap": {
        "ok": W(title="Sitemap found",
                summary="Your sitemap is listed in robots.txt and loads properly.",
                why="A sitemap lets search engines and AI agents find every page without guessing.",
                fix="Nothing to do.", offer="none"),
        "not_listed": W(title="Sitemap found",
                        summary="Your sitemap loads properly, but robots.txt does not point to it.",
                        why="A sitemap lets search engines and AI agents find every page. Listing it in robots.txt helps them find it first.",
                        fix="Add a Sitemap line to robots.txt.", offer="none"),
        "broken": W(title="Sitemap does not load",
                    summary="robots.txt points to a sitemap that does not load as a valid sitemap.",
                    why="Search engines and AI agents cannot use it to find your pages.",
                    fix="We repair the sitemap and keep it updated automatically.", offer="fixit"),
        "missing": W(title="No sitemap",
                     summary="We found no sitemap for your site.",
                     why="Without one, search engines and AI agents can only find pages by following links, and miss some.",
                     fix="We add a sitemap that updates itself and list it in robots.txt.", offer="fixit"),
    },
    "link_headers": {
        "ok": W(title="Points agents to machine-readable content",
                summary="Your homepage sends Link headers for: {rels_list}.",
                why="Agents can find your sitemap, API or Markdown version straight from the first response.",
                fix="Nothing to do.", offer="none"),
        "other_only": W(title="Link headers do not help agents",
                        summary="Your homepage sends Link headers ({rels_list}), but none point to machine-readable content.",
                        why="AI agents look in Link headers for a sitemap, Markdown version or API description.",
                        fix="We add Link headers that point agents to your sitemap and Markdown pages.", offer="fixit"),
        "missing": W(title="No Link headers for agents",
                     summary="Your homepage does not send Link headers.",
                     why="Link headers (RFC 8288) tell agents where your sitemap, Markdown version or API description lives, without reading the whole page.",
                     fix="We add Link headers that point agents to your sitemap and Markdown pages.", offer="fixit"),
    },
    "markdown": {
        "ok": W(title="Serves Markdown to AI agents",
                summary="When an agent asks for Markdown, your site sends Markdown instead of the full web page.",
                why="Agents read your content faster and more accurately, with far fewer tokens.",
                fix="Nothing to do.", offer="none"),
        "html_only": W(title="No Markdown version for AI agents",
                       summary="When an agent asks for Markdown (Accept: text/markdown), your site still sends the full web page.",
                       why="AI agents must strip menus, scripts and styling to find your content, and often get it wrong or give up.",
                       fix="We switch on Markdown for agents, for example through Cloudflare, so agents get clean text.", offer="fixit"),
    },
    "ai_rules": {
        "ok": W(title="Rules for AI crawlers are set",
                summary="robots.txt has rules for {named_count} AI crawlers, including {named_list}.",
                why="You decide which AI services may read your site, and AI assistants can still find you.",
                fix="Nothing to do.", offer="none"),
        "blocks_assistants": W(title="AI assistants are blocked",
                               summary="robots.txt blocks the AI assistants that answer people's questions: {blocked_list}.",
                               why="ChatGPT, Claude and Perplexity cannot read your site, so they will not recommend you when people ask.",
                               fix="We keep training crawlers out if you wish, and let AI assistants read and recommend you.", offer="fixit"),
        "wildcard": W(title="AI assistants may read your site",
                      summary="robots.txt has no rules for AI crawlers by name, so its general rules let them in.",
                      why="AI assistants can read and recommend your site. Naming them lets you choose, for example, to allow assistants but not training.",
                      fix="Nothing required. We can add named rules if you want finer control.", offer="none"),
        "no_robots": W(title="No rules for AI crawlers",
                       summary="Your site has no robots.txt, so there are no rules for AI crawlers.",
                       why="You have not decided which AI services may use your content, and agents have no clear signal.",
                       fix="We publish robots.txt with clear rules for AI crawlers.", offer="fixit"),
    },
    "content_signals": {
        "ok": W(title="Content Signals are set",
                summary="robots.txt says how AI may use your content: {signals_text}.",
                why="AI services know whether they may use your pages for search, for answers and for training.",
                fix="Nothing to do.", offer="none"),
        "invalid": W(title="Content Signals are not readable",
                     summary="robots.txt has a Content-Signal line, but not in a form agents understand.",
                     why="AI services cannot tell whether they may use your pages for search, answers or training.",
                     fix="We rewrite it as search=yes, ai-input=yes, ai-train=no, or whatever you choose.", offer="fixit"),
        "missing": W(title="No Content Signals",
                     summary="robots.txt does not say how AI may use your content.",
                     why="Content Signals tell AI services whether they may use your pages for search, for answers and for training.",
                     fix="We add a Content-Signal line, for example search=yes, ai-input=yes, ai-train=no.", offer="fixit"),
        "no_robots": W(title="No Content Signals",
                       summary="Your site has no robots.txt, so it cannot say how AI may use your content.",
                       why="Content Signals tell AI services whether they may use your pages for search, for answers and for training.",
                       fix="We publish robots.txt with Content Signals that match what you want.", offer="fixit"),
    },
    "llms_txt": {
        "ok": W(title="llms.txt is published",
                summary="Your site has an llms.txt file that guides AI tools to your key pages.",
                why="Some AI tools read it to understand your site quickly. Optional, not scored.",
                fix="Nothing to do.", offer="none"),
        "missing": W(title="No llms.txt (optional)",
                     summary="Your site has no /llms.txt file. It is optional and does not affect your score.",
                     why="A few AI tools read it as a short guide to your key pages. Support is still limited.",
                     fix="We can add one when we set up AI agent readiness.", offer="none"),
    },

    "https": {
        "ok": W(title="HTTPS is on and enforced",
                summary="Visitors are always sent to the secure version of your site.",
                why="Encryption protects what visitors type, and browsers mark sites without it as \"Not secure\".",
                fix="Nothing to do.", offer="none"),
        "no_hsts": W(title="HTTPS works but is not locked in",
                     summary="Your site redirects to HTTPS but does not send the HSTS header.",
                     why="Without HSTS, a visitor on public Wi-Fi can be pushed back to the insecure version before the redirect happens.",
                     fix="We add the HSTS header to your web server so browsers always use HTTPS.", offer="fixit"),
        "no_redirect": W(title="Visitors can still open the insecure version",
                         summary="Your site answers on plain HTTP without redirecting to HTTPS.",
                         why="Anyone who types your address without https:// gets an unencrypted page that browsers label \"Not secure\".",
                         fix="We redirect all HTTP traffic to HTTPS and enable HSTS.", offer="fixit"),
        "no_https": W(title="Your site has no working HTTPS",
                      summary="We could not open your site securely over HTTPS.",
                      why="Browsers warn visitors away from sites without HTTPS, and Google ranks them lower.",
                      fix="We install a free certificate with automatic renewal and turn on HTTPS.", offer="fixit"),
    },
    "ssl": {
        "ok": W(title="SSL certificate is valid",
                summary="Valid certificate, {days_left} days until it expires, modern TLS only.",
                why="A valid certificate is what lets browsers show the padlock.",
                fix="Nothing to do.", offer="none"),
        "expiring": W(title="SSL certificate expires in {days_left} days",
                      summary="Your certificate is valid but expires on {expires}.",
                      why="When it expires, every visitor sees a full-page security warning.",
                      fix="We set up automatic renewal so it never lapses.", offer="fixit"),
        "expiring_soon": W(title="SSL certificate expires in {days_left} days",
                           summary="Your certificate expires on {expires}, which is very soon.",
                           why="When it expires, every visitor sees a full-page security warning and most will leave.",
                           fix="We renew it now and set up automatic renewal.", offer="fixit"),
        "legacy_tls": W(title="Old, insecure TLS versions are still allowed",
                        summary="Your server still accepts TLS 1.0 or 1.1, which were retired years ago.",
                        why="These versions have known weaknesses and fail most security compliance checks.",
                        fix="We switch your server to TLS 1.2 and 1.3 only.", offer="fixit"),
        "expired": W(title="SSL certificate has expired",
                     summary="Your certificate expired on {expires}. Browsers are blocking visitors with a warning.",
                     why="Most visitors leave as soon as they see the warning page.",
                     fix="We install a new certificate today and set up automatic renewal.", offer="fixit"),
        "hostname": W(title="SSL certificate does not match your domain",
                      summary="The certificate was issued for a different name than {host}.",
                      why="Browsers show a security warning, exactly as if the certificate were missing.",
                      fix="We issue a certificate that covers your domain and its www version.", offer="fixit"),
        "self_signed": W(title="SSL certificate is not trusted",
                         summary="Your site uses a self-signed certificate that browsers do not trust.",
                         why="Every visitor sees a security warning before reaching your site.",
                         fix="We replace it with a free, trusted certificate that renews itself.", offer="fixit"),
        "incomplete_chain": W(title="SSL certificate chain is incomplete",
                              summary="Your server sends its certificate without the middle certificate that links it to a trusted authority.",
                              why="Desktop browsers often cope, but many phones, apps and payment services show an error or refuse to connect.",
                              fix="We install the full certificate chain, so every device trusts it.", offer="fixit"),
        "invalid": W(title="SSL certificate is not valid",
                     summary="Browsers reject your certificate: {verify_error}.",
                     why="Visitors see a security warning instead of your site.",
                     fix="We install a valid certificate with automatic renewal.", offer="fixit"),
        "no_https": W(title="No SSL certificate found",
                      summary="Nothing answered securely on port 443.",
                      why="Without a certificate there is no padlock and browsers mark the site \"Not secure\".",
                      fix="We install a free certificate with automatic renewal.", offer="fixit"),
    },
    "headers": {
        "ok": W(title="Security headers are in place",
                summary="{count} of 5 recommended security headers are set.",
                why="These headers tell browsers to block common attacks on your visitors.",
                fix="Nothing to do.", offer="none"),
        "some_missing": W(title="Some security headers are missing",
                          summary="Only {count} of 5 recommended headers are set. Missing: {missing_list}.",
                          why="Each missing header leaves a door open to attacks such as clickjacking or script injection.",
                          fix="We add the missing headers and test that your site still works.", offer="security_shield"),
        "none_set": W(title="Security headers are missing",
                      summary="None of the 5 recommended security headers are set.",
                      why="Browsers have no instructions to protect your visitors from clickjacking and script injection.",
                      fix="We add the headers and put a web application firewall in front of your site.", offer="security_shield"),
        "most_missing": W(title="Security headers are missing",
                          summary="Only {count} of 5 recommended headers are set. Missing: {missing_list}.",
                          why="Browsers have no instructions to protect your visitors from clickjacking and script injection.",
                          fix="We add the headers and put a web application firewall in front of your site.", offer="security_shield"),
    },
    "software": {
        "ok": W(title="No software versions on show",
                summary="Your server does not reveal which software versions it runs.",
                why="Hidden versions make it harder for attackers to pick a known weakness.",
                fix="Nothing to do.", offer="none"),
        "visible": W(title="Your server reveals its software versions",
                     summary="Anyone can see: {visible_list}.",
                     why="Attackers scan for exact versions to match them with known weaknesses.",
                     fix="We hide version details and keep the software patched.", offer="fixit"),
        "outdated": W(title="Outdated software detected",
                      summary="Your site runs software that no longer gets security fixes: {outdated_list}.",
                      why="Unsupported software is the most common way small business sites get hacked.",
                      fix="We update and harden the server, then keep it patched every month.", offer="cloudcare"),
    },
    "uptime": {
        "ok": W(title="Fast and responding",
                summary="Your server answered every request, in about {ttfb_ms} ms.",
                why="A quick first response keeps visitors and search engines happy.",
                fix="Nothing to do.", offer="none"),
        "slowish": W(title="Server is slow to respond",
                     summary="Your server took about {ttfb_ms} ms to start answering. Under 800 ms is good.",
                     why="Slow responses make every page feel sluggish, especially on mobile data.",
                     fix="We move your site to a tuned MAKTECH server with caching.", offer="cloudcare"),
        "slow": W(title="Server is very slow to respond",
                  summary="Your server took about {ttfb_ms} ms to start answering. Under 800 ms is good.",
                  why="Many visitors give up before the page appears, and Google ranks slow sites lower.",
                  fix="We move your site to a tuned MAKTECH server with caching.", offer="cloudcare"),
        "unstable": W(title="Server failed during our test",
                      summary="Some of our requests failed ({errors_list}).",
                      why="If it fails for us, it fails for your customers too.",
                      fix="We monitor your site around the clock and host it on a stable server.", offer="cloudcare"),
        "down": W(title="Your site did not respond",
                  summary="None of our requests got an answer ({errors_list}).",
                  why="Every minute your site is down, customers see an error instead of your business.",
                  fix="We find the cause, bring it back and monitor it 24/7.", offer="cloudcare"),
    },
    "domain_expiry": {
        "ok": W(title="Domain registration is safe",
                summary="Your domain is registered until {expires}.",
                why="An expired domain takes your website and email offline at once.",
                fix="Nothing to do.", offer="none"),
        "soon": W(title="Domain expires in {days_left} days",
                  summary="Your domain registration ends on {expires}.",
                  why="If it lapses, your website and email stop working and someone else can buy the name.",
                  fix="We track renewal dates for you and remind you in time.", offer="cloudcare"),
        "very_soon": W(title="Domain expires in {days_left} days",
                       summary="Your domain registration ends on {expires}. Renew it now.",
                       why="If it lapses, your website and email stop working and someone else can buy the name.",
                       fix="We help you renew today and track the date from now on.", offer="fixit"),
    },
    "dns": {
        "ok": W(title="DNS is healthy",
                summary="{ns_count} nameservers, all answering correctly.",
                why="DNS is what points your domain to your site and email.",
                fix="Nothing to do.", offer="none"),
        "some_lame": W(title="Some nameservers are not answering",
                       summary="Not answering: {not_responding_list}.",
                       why="Visitors whose lookups hit a broken nameserver may not reach your site.",
                       fix="We clean up your DNS so every nameserver answers.", offer="fixit"),
        "single_ns": W(title="Only one nameserver",
                       summary="Your domain relies on a single nameserver.",
                       why="If that one server has a problem, your website and email disappear.",
                       fix="We move your DNS to a provider with several redundant nameservers.", offer="fixit"),
        "none_responding": W(title="Nameservers are not answering",
                             summary="None of your nameservers answered for your domain.",
                             why="Your website and email may be unreachable for many people.",
                             fix="We fix your DNS setup straight away.", offer="fixit"),
        "no_ns": W(title="No nameservers found",
                   summary="We found no nameservers for {apex}.",
                   why="Without working DNS, nobody can reach your site or send you email.",
                   fix="We set up reliable DNS for your domain.", offer="fixit"),
    },
    "spf": {
        "ok": W(title="SPF is set up",
                summary="Your domain lists which servers may send its email.",
                why="SPF helps your emails reach inboxes and stops others sending as you.",
                fix="Nothing to do.", offer="none"),
        "missing": W(title="SPF record is missing",
                     summary="Your domain does not say which servers may send its email.",
                     why="Your emails are more likely to land in spam, and anyone can pretend to send email as you.",
                     fix="We add a correct SPF record for every service that sends your email.", offer="email_setup"),
        "multiple": W(title="More than one SPF record",
                      summary="Your domain has several SPF records, which makes all of them invalid.",
                      why="Mail servers treat this as an error, so your SPF protection does not work at all.",
                      fix="We merge them into one correct record.", offer="email_setup"),
        "plus_all": W(title="SPF allows anyone to send as you",
                      summary="Your SPF record ends in \"+all\", which approves every server on the internet.",
                      why="It gives spammers permission to send email in your name.",
                      fix="We rewrite the record to allow only your real mail services.", offer="email_setup"),
        "too_many_lookups": W(title="SPF record is too complex",
                              summary="Checking your SPF needs {lookups} DNS lookups; the limit is 10.",
                              why="Over the limit, mail servers treat your SPF as broken and may reject your mail.",
                              fix="We flatten and simplify the record to fit the limit.", offer="email_setup"),
        "broken_include": W(title="SPF points to a missing record",
                            summary="Your SPF includes a domain with no valid SPF: {broken_includes_list}.",
                            why="Some mail servers will treat your SPF as broken.",
                            fix="We remove or correct the broken entry.", offer="email_setup"),
        "no_all": W(title="SPF record is incomplete",
                    summary="Your SPF record does not say what to do with unknown senders.",
                    why="Mail servers fall back to accepting email from anyone claiming to be you.",
                    fix="We finish the record with a safe \"~all\" or \"-all\" ending.", offer="email_setup"),
        "near_limit": W(title="SPF record is close to its limit",
                        summary="Checking your SPF needs {lookups} DNS lookups; the limit is 10.",
                        why="Add one more email service (a newsletter tool or CRM) and SPF breaks, sending your mail to spam.",
                        fix="We simplify the record now, so there is room to grow.", offer="email_setup"),
        "neutral": W(title="SPF record is too relaxed",
                     summary="Your SPF ends in \"?all\", so unknown senders are neither allowed nor blocked.",
                     why="It gives almost no protection against people sending as you.",
                     fix="We tighten it to \"~all\" or \"-all\".", offer="email_setup"),
    },
    "dkim": {
        "ok": W(title="DKIM is set up",
                summary="We found a DKIM key ({selectors_list}).",
                why="DKIM signs your emails so receivers can tell they really came from you.",
                fix="Nothing to do.", offer="none"),
        "not_found": W(title="DKIM not found",
                       summary="We did not find a DKIM key under the common names. It may exist under a name we did not try.",
                       why="Without DKIM, your emails are more likely to land in spam.",
                       fix="We check your mail provider and publish the DKIM key.", offer="email_setup"),
    },
    "dmarc": {
        "ok": W(title="DMARC is protecting your domain",
                summary="Your DMARC policy is \"{policy}\".",
                why="DMARC tells receivers to reject email that fakes your domain.",
                fix="Nothing to do.", offer="none"),
        "monitor_only": W(title="DMARC is only watching",
                          summary="Your DMARC policy is \"none\", so fake emails are still delivered.",
                          why="Scammers can still send convincing email in your name to your customers.",
                          fix="We move you safely to \"quarantine\" and then \"reject\".", offer="email_setup"),
        "missing": W(title="DMARC record is missing",
                     summary="Your domain has no DMARC policy.",
                     why="Anyone can send email that looks like it came from you, and big providers now expect DMARC.",
                     fix="We add a DMARC record and reporting, then tighten it step by step.", offer="email_setup"),
        "multiple": W(title="More than one DMARC record",
                      summary="Your domain has several DMARC records, so receivers ignore all of them.",
                      why="Your domain has no working DMARC protection.",
                      fix="We merge them into one correct record.", offer="email_setup"),
        "invalid": W(title="DMARC record is not valid",
                     summary="Your DMARC record has no valid policy.",
                     why="Receivers ignore it, so your domain is unprotected.",
                     fix="We correct the record.", offer="email_setup"),
    },
    "blacklist": {
        "ok": W(title="Not on any blocklist",
                summary="Your {source} address is clean on the lists we checked.",
                why="Being listed sends your email straight to spam or gets it rejected.",
                fix="Nothing to do.", offer="none"),
        "listed": W(title="Listed on an email blocklist",
                    summary="Your {source} address is on: {listed_list}.",
                    why="Many receivers reject or spam-folder every email from a listed address.",
                    fix="We find the cause, clean it up and request removal.", offer="email_setup"),
    },
    "mta_sts": {
        "ok": W(title="Incoming mail is always encrypted",
                summary="Your domain publishes an MTA-STS policy ({mode} mode) and asks for TLS reports.",
                why="Other mail servers must use checked encryption when they deliver to you, so nobody can read your mail on the way.",
                fix="Nothing to do.", offer="none"),
        "missing": W(title="Incoming mail encryption is optional",
                     summary="Your domain has no MTA-STS policy and no TLS reporting.",
                     why="Mail sent to you may fall back to no encryption without anyone noticing. Larger customers and banks increasingly expect this.",
                     fix="We publish an MTA-STS policy and TLS reporting for your domain.", offer="email_setup"),
        "no_tlsrpt": W(title="No reports on mail encryption",
                       summary="Your MTA-STS policy is set, but your domain does not ask for TLS reports.",
                       why="If encrypted delivery to you starts failing, nobody tells you.",
                       fix="We add a TLS reporting record and watch the reports for you.", offer="email_setup"),
        "no_sts": W(title="Incoming mail encryption is optional",
                    summary="Your domain asks for TLS reports but has no MTA-STS policy.",
                    why="Without the policy, mail sent to you may still fall back to no encryption.",
                    fix="We publish an MTA-STS policy to go with your reporting.", offer="email_setup"),
        "broken_policy": W(title="MTA-STS policy does not load",
                           summary="Your DNS announces MTA-STS, but the policy file at mta-sts.{apex} does not load properly.",
                           why="Mail servers ignore a policy they cannot read, so the protection is not working.",
                           fix="We publish the policy file over HTTPS with a valid certificate.", offer="email_setup"),
    },
    "mobile_speed": {
        "ok": W(title="Fast on mobile",
                summary="{tester} scores your site {score} out of 100 on a mid-range phone.",
                why="Most of your visitors are on phones; speed keeps them on the page.",
                fix="Nothing to do.", offer="none"),
        "average": W(title="Average speed on mobile",
                     summary="{tester} scores your site {score} out of 100 on a mid-range phone. 90 or more is good.",
                     why="Every extra second of loading loses visitors, and speed affects your Google ranking.",
                     fix="We tune your server, compress images and add caching.", offer="cloudcare"),
        "poor": W(title="Slow on mobile",
                  summary="{tester} scores your site {score} out of 100 on a mid-range phone. 90 or more is good.",
                  why="Slow mobile pages lose most visitors before they load and rank lower on Google.",
                  fix="We move you to a tuned MAKTECH server, compress images and add caching.", offer="cloudcare"),
    },
    "web_vitals": {
        "ok": W(title="Core Web Vitals pass",
                summary="Main content appears in {lcp_s} s, the layout stays stable and the page responds quickly.",
                why="Google uses these measures in its rankings.",
                fix="Nothing to do.", offer="none"),
        "needs_work": W(title="Core Web Vitals need work",
                        summary="Main content appears in {lcp_s} s (good: 2.5 s or less), layout shift {cls} (good: 0.1 or less), busy for {tbt_ms} ms (good: 200 ms or less).",
                        why="Google uses these measures in its rankings, and visitors notice the wait.",
                        fix="We optimise images, fonts and caching to bring them into the green.", offer="cloudcare"),
        "poor": W(title="Core Web Vitals fail",
                  summary="Main content appears in {lcp_s} s (good: 2.5 s or less), layout shift {cls} (good: 0.1 or less), busy for {tbt_ms} ms (good: 200 ms or less).",
                  why="Visitors wait too long or see the page jump around, and Google ranks it lower.",
                  fix="We optimise images, fonts and caching and move you to a faster server.", offer="cloudcare"),
    },

    "exposed_files": {
        "ok": W(title="No private files are exposed",
                summary="We looked for {checked} kinds of files that should never be public and found none.",
                why="Leaked settings files, backups and code folders are one of the most common ways sites get hacked.",
                fix="Nothing to do.", offer="none"),
        "exposed": W(title="Private files can be downloaded from your site",
                     summary="Anyone can download: {found_list}.",
                     why="These files can hold passwords, keys or your whole database. Attackers scan for them automatically, every day.",
                     fix="We remove the files today, block the paths on your server, and change any passwords they contained.",
                     offer="security_shield"),
        "info_page": W(title="A server information page is public",
                       summary="Anyone can open: {found_list}.",
                       why="It shows attackers exactly which software and settings your server runs, which makes them easier to target.",
                       fix="We remove the page and check the server for other leftovers.", offer="security_shield"),
        "minor": W(title="Some server details are visible",
                   summary="Anyone can open: {found_list}.",
                   why="It is not a direct risk on its own, but it tells attackers more about your site than they need to know.",
                   fix="We remove the files and block them on your server.", offer="security_shield"),
    },
    "directory_listing": {
        "ok": W(title="Folders are not open for browsing",
                summary="Your server does not list the files inside its folders.",
                why="Open folders let anyone browse every file you have uploaded.",
                fix="Nothing to do.", offer="none"),
        "listed": W(title="Folders on your site can be browsed",
                    summary="Anyone can see a list of every file in: {folders_list}.",
                    why="Uploaded invoices, forms and private documents become easy to find, even if they were never linked.",
                    fix="We switch off folder listings on your server and check what was exposed.", offer="security_shield"),
        "backup_listed": W(title="Your backup folder can be browsed",
                           summary="Anyone can see and download the files in: {folders_list}.",
                           why="Backups usually contain your whole site and database, including passwords.",
                           fix="We move the backups somewhere private today and switch off folder listings.", offer="security_shield"),
    },
    "mixed_content": {
        "ok": W(title="Everything on the page loads securely",
                summary="Your homepage loads all its files over HTTPS.",
                why="Mixing in insecure files breaks the padlock and can let attackers change the page.",
                fix="Nothing to do.", offer="none"),
        "passive": W(title="Some images load insecurely",
                     summary="{passive_count} image or media files load over plain HTTP.",
                     why="Browsers may hide the padlock or block these files, so parts of the page can look broken.",
                     fix="We switch every file to HTTPS so the padlock stays solid.", offer="fixit"),
        "active": W(title="Insecure scripts or styles on a secure page",
                    summary="{active_count} scripts, styles, frames or forms load over plain HTTP.",
                    why="Browsers block these files, so parts of your site may not work, and the page can be tampered with.",
                    fix="We switch every file and form to HTTPS and test the site in all major browsers.", offer="fixit"),
    },
    "cookies": {
        "ok": W(title="Cookies are set safely",
                summary="Your cookies use the Secure and SameSite settings.",
                why="Safe cookie settings stop visitors' sessions being stolen.",
                fix="Nothing to do.", offer="none"),
        "none": W(title="No cookies on the homepage",
                  summary="Your homepage does not set any cookies.",
                  why="There is nothing here that could leak a visitor's session.",
                  fix="Nothing to do.", offer="none"),
        "flags_missing": W(title="Some cookies miss safety settings",
                           summary="Cookies without full protection: {weak_list}.",
                           why="Without the Secure and SameSite settings, cookies can be sent over insecure connections or to other sites.",
                           fix="We update your site and server so every cookie is set safely.", offer="security_shield"),
        "session_unsafe": W(title="Sign-in cookies can be stolen",
                            summary="Session or sign-in cookies are missing the Secure or HttpOnly setting.",
                            why="A stolen session cookie lets an attacker act as a signed-in user without the password.",
                            fix="We lock down your session cookies and check the sign-in setup.", offer="security_shield"),
    },
    "security_txt": {
        "ok": W(title="Security contact is published",
                summary="Your site has a security.txt file with a contact address.",
                why="People who find a problem on your site know where to report it.",
                fix="Nothing to do.", offer="none"),
        "missing": W(title="No security contact published",
                     summary="Your site has no /.well-known/security.txt file.",
                     why="If someone finds a security problem on your site, they have no clear way to tell you before it is misused.",
                     fix="We publish a security.txt file with the right contact address.", offer="security_shield"),
    },
    "dnssec": {
        "ok": W(title="DNSSEC is switched on",
                summary="Your domain's DNS answers are signed.",
                why="Signed answers stop attackers sending your visitors to a fake copy of your site.",
                fix="Nothing to do.", offer="none"),
        "off": W(title="DNSSEC is not switched on",
                 summary="Your domain's DNS answers are not signed.",
                 why="Without it, some attacks can quietly send visitors or email to a fake server.",
                 fix="We switch on DNSSEC with your DNS host and registrar.", offer="fixit"),
    },
    "meta_tags": {
        "ok": W(title="Page title and description are set",
                summary="Your homepage has a clear title ({title_len} characters) and a description.",
                why="This is the text people see for your site in Google results.",
                fix="Nothing to do.", offer="none"),
        "no_title": W(title="Your homepage has no title",
                      summary="Google and browser tabs have no name to show for your site.",
                      why="The title is the first thing people see in search results, and pages without one rank poorly.",
                      fix="We write a clear title and description for your key pages.", offer="fixit"),
        "no_description": W(title="Your homepage has no description",
                            summary="There is no meta description, so Google picks random text from the page.",
                            why="A good description makes more people click your site in search results.",
                            fix="We write descriptions for your key pages.", offer="fixit"),
        "title_length": W(title="Page title is too short or too long",
                          summary="Your title is {title_len} characters. Between 10 and 70 works best.",
                          why="Google cuts long titles off, and very short ones do not say what you do.",
                          fix="We rewrite the title so it reads well in search results.", offer="fixit"),
        "description_length": W(title="Page description is too short or too long",
                                summary="Your description is {desc_len} characters. Between 50 and 170 works best.",
                                why="Google cuts long descriptions off, and short ones waste the chance to win the click.",
                                fix="We rewrite the description so it reads well in search results.", offer="fixit"),
    },
    "mobile_viewport": {
        "ok": W(title="Set up for phones",
                summary="Your page tells phones to fit it to the screen.",
                why="Most visitors arrive on a phone, and Google ranks sites by their mobile version.",
                fix="Nothing to do.", offer="none"),
        "missing": W(title="Not set up for phones",
                     summary="Your page has no mobile viewport setting, so phones show a shrunken desktop page.",
                     why="Visitors have to pinch and zoom, most leave, and Google ranks the site lower.",
                     fix="We make your site responsive so it fits every screen.", offer="fixit"),
        "fixed_width": W(title="Page does not fit phone screens",
                         summary="Your viewport setting uses a fixed width instead of the phone's width.",
                         why="Phones show the page too wide or too small, and Google marks it as not mobile-friendly.",
                         fix="We make your site responsive so it fits every screen.", offer="fixit"),
        "no_zoom": W(title="Visitors cannot zoom on phones",
                     summary="Your page stops visitors from zooming in.",
                     why="People with weaker eyesight cannot read your content, and it fails accessibility guidelines.",
                     fix="We allow zooming while keeping the layout tidy.", offer="fixit"),
    },
    "indexing": {
        "ok": W(title="Google can find and read your site",
                summary="Nothing blocks search engines, and your site has a sitemap.",
                why="A sitemap helps Google find every page quickly.",
                fix="Nothing to do.", offer="none"),
        "no_sitemap": W(title="No sitemap found",
                        summary="We could not find a sitemap for your site.",
                        why="Without one, Google can be slow to find new or deeper pages.",
                        fix="We add a sitemap and submit it to Google Search Console.", offer="fixit"),
        "noindex": W(title="Your homepage is hidden from Google",
                     summary="The page tells search engines not to list it (noindex).",
                     why="Your site will not appear in Google results at all. This is often left over from building the site.",
                     fix="We remove the block and ask Google to list your site again.", offer="fixit"),
        "blocked": W(title="robots.txt blocks search engines",
                     summary="Your robots.txt file tells search engines to stay out of the whole site.",
                     why="Google cannot read your pages, so they drop out of search results.",
                     fix="We fix robots.txt and ask Google to read your site again.", offer="fixit"),
    },
    "canonical": {
        "ok": W(title="Main page address is set",
                summary="Your homepage tells search engines its main address: {canonical}.",
                why="Google combines the www, non-www and tracking-link versions of a page into one, so they do not compete.",
                fix="Nothing to do.", offer="none"),
        "missing": W(title="No main page address",
                     summary="Your homepage does not tell search engines its main address (canonical link).",
                     why="Google may treat the www, non-www and tracking-link versions as separate pages and split your ranking between them.",
                     fix="We add a canonical link to every page.", offer="fixit"),
        "other_site": W(title="Main page address points to another site",
                        summary="Your homepage says its main address is {canonical}, which is on a different domain.",
                        why="Google may drop your page from results and show the other address instead.",
                        fix="We point the canonical link back to your own domain.", offer="fixit"),
        "insecure": W(title="Main page address uses http",
                      summary="Your canonical link points to {canonical}, the insecure version of your page.",
                      why="It tells Google to prefer the version without the padlock.",
                      fix="We change it to the https address.", offer="fixit"),
    },
    "structured_data": {
        "ok": W(title="Business details are marked up for Google",
                summary="Your homepage describes your business ({business}) in a format search engines read.",
                why="Google can show your phone number, address and opening hours right in search results and Maps.",
                fix="Nothing to do.", offer="none"),
        "incomplete": W(title="Business details are incomplete",
                        summary="Your homepage describes your business ({business}), but leaves out: {missing_list}.",
                        why="Google cannot show your contact details in search results without them.",
                        fix="We complete your business details: name, phone, address and opening hours.", offer="fixit"),
        "no_business": W(title="No business details for Google",
                         summary="Your homepage has structured data ({types_list}), but none that describes your business.",
                         why="Google and AI assistants have to guess your phone number, address and opening hours.",
                         fix="We add your business details in the format Google reads (schema.org).", offer="fixit"),
        "missing": W(title="No business details for Google",
                     summary="Your homepage has no structured data (schema.org) about your business.",
                     why="Google and AI assistants have to guess your phone number, address and opening hours, and often get them wrong.",
                     fix="We add your business name, phone, address and opening hours in the format Google reads.", offer="fixit"),
        "invalid": W(title="Business details cannot be read",
                     summary="Your homepage has structured data, but it contains errors and cannot be read.",
                     why="Search engines ignore it, so your details do not show in results.",
                     fix="We repair the markup and test it with Google's tools.", offer="fixit"),
    },
    "error_page": {
        "ok": W(title="Missing pages are handled properly",
                summary="A page that does not exist answers with a proper \"not found\" (error {status}).",
                why="Search engines drop dead links instead of listing them.",
                fix="Nothing to do.", offer="none"),
        "soft_404": W(title="Missing pages look like real pages",
                      summary="A page that does not exist answers \"OK\" (status 200) instead of \"not found\".",
                      why="Google may list empty or duplicate pages and trust your site less.",
                      fix="We set up a proper 404 page that helps visitors find their way.", offer="fixit"),
        "redirects": W(title="Missing pages redirect elsewhere",
                       summary="A page that does not exist redirects (status {status}) instead of saying \"not found\".",
                       why="Google treats this as a hidden error, and visitors land somewhere they did not expect.",
                       fix="We set up a proper 404 page that helps visitors find their way.", offer="fixit"),
        "server_error": W(title="Missing pages cause a server error",
                          summary="A page that does not exist answers with a server error (status {status}).",
                          why="It looks like your site is broken, to visitors and to Google.",
                          fix="We fix the error handling and add a proper 404 page.", offer="fixit"),
    },
    "social_preview": {
        "ok": W(title="Links to your site look good when shared",
                summary="Your page has a sharing title and image, and a site icon.",
                why="Shared links on WhatsApp and Facebook show a proper preview card.",
                fix="Nothing to do.", offer="none"),
        "no_favicon": W(title="No site icon",
                        summary="Your sharing preview is set, but the site has no icon (favicon).",
                        why="Browser tabs, bookmarks and Google results show a blank icon instead of your logo.",
                        fix="We add your logo as the site icon.", offer="fixit"),
        "partial": W(title="Sharing preview is incomplete",
                     summary="Missing: {missing_list}.",
                     why="Links shared on WhatsApp and Facebook show without a proper title or picture, so fewer people tap them.",
                     fix="We add a sharing title, description and image to your pages.", offer="fixit"),
        "none": W(title="No sharing preview",
                  summary="Your page has no sharing title, description or image (Open Graph tags).",
                  why="Links shared on WhatsApp and Facebook look plain, so fewer people tap them.",
                  fix="We add a sharing title, description and image to your pages.", offer="fixit"),
    },
    "accessibility": {
        "ok": W(title="Easy to use for everyone",
                summary="{tester} rates your homepage's accessibility {score} out of 100.",
                why="People with weak eyesight or using screen readers can use your site, and so can Google.",
                fix="Nothing to do.", offer="none"),
        "minor": W(title="Easy to use for everyone",
                   summary="{tester} rates your homepage's accessibility {score} out of 100. Small things to tidy up: {issues_list}.",
                   why="People with weak eyesight or using screen readers can mostly use your site.",
                   fix="We tidy up the remaining details.", offer="none"),
        "some_issues": W(title="Accessibility needs work",
                         summary="{tester} rates your homepage's accessibility {score} out of 100. Problems found: {issues_list}.",
                         why="Hard-to-read text and unlabelled buttons lose older visitors and people on small screens. 90 or more is good.",
                         fix="We fix contrast, labels and image descriptions across your site.", offer="fixit"),
        "many_issues": W(title="Hard to use for many visitors",
                         summary="{tester} rates your homepage's accessibility {score} out of 100. Problems found: {issues_list}.",
                         why="Many visitors, especially older ones and people with weak eyesight, cannot read or use parts of your site.",
                         fix="We fix contrast, labels and image descriptions across your site.", offer="fixit"),
    },
    "headings": {
        "ok": W(title="Clear main heading",
                summary="Your homepage has one main heading: \"{h1}\".",
                why="Google and visitors see at a glance what the page is about.",
                fix="Nothing to do.", offer="none"),
        "no_h1": W(title="No main heading",
                   summary="Your homepage has no main heading (H1).",
                   why="The main heading is one of the strongest hints to Google about what your page is about.",
                   fix="We add one clear main heading with the words your customers search for.", offer="fixit"),
        "many_h1": W(title="Several main headings",
                     summary="Your homepage has {h1_count} main headings (H1). One is best.",
                     why="Google gets mixed signals about what the page is mainly about.",
                     fix="We keep one main heading and turn the rest into subheadings.", offer="fixit"),
        "skipped": W(title="Headings skip a level",
                     summary="Your headings jump from {skipped}, skipping a level.",
                     why="Screen readers and search engines use the heading order to understand the page.",
                     fix="We put the headings in order.", offer="fixit"),
    },
    "image_alt": {
        "ok": W(title="Images are described",
                summary="Every image on your homepage ({images}) has a description (alt text).",
                why="Google Images and screen readers know what each picture shows.",
                fix="Nothing to do.", offer="none"),
        "no_images": W(title="Images are described",
                       summary="Your homepage has no images that need a description.",
                       why="Nothing to describe.",
                       fix="Nothing to do.", offer="none"),
        "some_missing": W(title="Some images have no description",
                          summary="{missing_count} of {images} images have no description (alt text), for example: {examples_list}.",
                          why="Google Images cannot list them and screen readers cannot tell blind visitors what they show.",
                          fix="We add short, useful descriptions to your images.", offer="fixit"),
        "most_missing": W(title="Most images have no description",
                          summary="{missing_count} of {images} images have no description (alt text), for example: {examples_list}.",
                          why="Google Images cannot list them and screen readers cannot tell blind visitors what they show.",
                          fix="We add short, useful descriptions to your images.", offer="fixit"),
    },
    "content_depth": {
        "ok": W(title="Enough text on the homepage",
                summary="Your homepage has about {words} words of text.",
                why="Search engines and AI assistants have enough to understand what you offer.",
                fix="Nothing to do.", offer="none"),
        "thin": W(title="Little text on the homepage",
                  summary="Your homepage has only about {words} words of text.",
                  why="Search engines and AI assistants have little to go on, so you show up for fewer searches.",
                  fix="We help you write clear text about your services, area and prices.", offer="fixit"),
        "very_thin": W(title="Almost no text on the homepage",
                       summary="Your homepage has only about {words} words of text.",
                       why="Search engines and AI assistants cannot tell what you offer, so you rarely show up in searches.",
                       fix="We help you write clear text about your services, area and prices.", offer="fixit"),
        "script_only": W(title="Text only appears after scripts run",
                         summary="Your homepage arrives almost empty ({words} words) and builds its text with JavaScript.",
                         why="Google can usually wait for it, but most AI assistants and social apps read the empty version.",
                         fix="We set up pre-rendering, so every visitor and bot gets the full text at once.", offer="fixit"),
        "needs_scripts": W(title="Text only appears after scripts run",
                           summary="Your homepage arrives with {raw_words} words; the other text (about {words} words) is built with JavaScript.",
                           why="Google can usually wait for it, but most AI assistants and social apps read the empty version.",
                           fix="We set up pre-rendering, so every visitor and bot gets the full text at once.", offer="fixit"),
    },
    "contact_info": {
        "ok": W(title="Contact details are easy to find",
                summary="Your homepage shows: {found_list}.",
                why="Visitors ready to buy can reach you straight away.",
                fix="Nothing to do.", offer="none"),
        "contact_page_only": W(title="No contact details on the homepage",
                               summary="Your homepage links to a contact page, but shows no phone number or email itself.",
                               why="Every extra click loses some visitors who were ready to call.",
                               fix="We add a visible phone number, WhatsApp button and email to your homepage.", offer="fixit"),
        "none": W(title="No contact details found",
                  summary="We found no phone number, email or contact page on your homepage.",
                  why="Visitors ready to buy cannot reach you, and Google trusts businesses with clear contact details more.",
                  fix="We add a visible phone number, WhatsApp button and email to your homepage.", offer="fixit"),
    },
    "page_basics": {
        "ok": W(title="Page basics are in place",
                summary="Your homepage declares its language, character set and document type.",
                why="Browsers, translators and screen readers show your page correctly.",
                fix="Nothing to do.", offer="none"),
        "missing": W(title="Page basics are missing",
                     summary="Your homepage does not declare its: {missing_list}.",
                     why="Browsers may show garbled characters, offer the wrong translation, or read it aloud in the wrong language.",
                     fix="We add the missing declarations to your page template.", offer="fixit"),
    },
}

NOT_CHECKED = {
    "unreachable": "We could not load your homepage, so this was not checked.",
    "lookup_failed": "The lookup did not get an answer in time, so this was not checked.",
    "speed_failed": "Our speed test could not finish this time, so this was not checked.",
    "speed_page_error": "Your homepage did not finish loading in our test browser, so this was not checked.",
    "speed_blocked": "Your site's bot protection or firewall turned our test browser away, so this was not checked.",
    "no_rdap": "Your domain's registry does not publish expiry dates online, so this was not checked.",
    "no_date": "The registry did not share an expiry date, so this was not checked.",
    "not_configured": "This check is not switched on yet.",
    "no_ip": "We found no address to check.",
    "no_https_page": "Your site does not load over working HTTPS, so this was not checked.",
    "not_html": "Your homepage did not return a normal web page, so this was not checked.",
    "no_mx": "Your domain does not receive email, so this was not checked.",
}


# Accessibility problems Lighthouse reports, in plain words (by audit id).
A11Y_ISSUES = {
    "color-contrast": "text with too little contrast",
    "image-alt": "images without a description",
    "link-name": "links without readable text",
    "button-name": "buttons without a name",
    "label": "form fields without a label",
    "html-has-lang": "no page language",
    "html-lang-valid": "an invalid page language",
    "valid-lang": "an invalid language code",
    "document-title": "no page title",
    "heading-order": "headings out of order",
    "landmark-one-main": "no main content area",
    "meta-viewport": "zooming switched off",
    "list": "badly built lists",
    "listitem": "badly built lists",
    "frame-title": "embedded frames without a title",
    "input-image-alt": "image buttons without a description",
    "select-name": "drop-downs without a label",
    "label-content-name-mismatch": "labels that differ from the visible text",
    "target-size": "tap targets that are too small",
    "duplicate-id-aria": "duplicate element ids",
    "image-redundant-alt": "image descriptions that repeat nearby text",
    "skip-link": "a broken skip link",
    "bypass": "no way to skip the menu",
    "tabindex": "a confusing keyboard order",
    "video-caption": "videos without captions",
    "object-alt": "embedded objects without a description",
    "meta-refresh": "a page that refreshes itself",
    "link-in-text-block": "links that look like plain text",
    "identical-links-same-purpose": "identical links that go to different places",
    "td-headers-attr": "badly labelled tables",
    "th-has-data-cells": "badly labelled tables",
    "definition-list": "badly built lists",
    "dlitem": "badly built lists",
    "form-field-multiple-labels": "form fields with several labels",
    "input-button-name": "buttons without a name",
    "accesskeys": "clashing keyboard shortcuts",
    "aria": "screen reader labels (ARIA) set up wrongly",
}

# The changes that would save the most loading time (by Lighthouse audit id).
SPEED_FIXES = {
    "render-blocking-insight": ("Stop files from blocking the first view",
                                "Styles and scripts load before anything appears. Load them later, or inline the small part the first screen needs."),
    "image-delivery-insight": ("Compress and resize images",
                               "Serve images as WebP or AVIF, at the size they are shown."),
    "offscreen-images": ("Load images further down the page later",
                         "Images below the first screen load before the visitor scrolls to them."),
    "unused-javascript": ("Remove unused JavaScript",
                          "Scripts are downloaded, but most of their code never runs on this page."),
    "unused-css-rules": ("Remove unused CSS",
                         "Style sheets carry many rules this page never uses."),
    "unminified-javascript": ("Minify JavaScript", "Scripts are sent with spaces and comments left in."),
    "unminified-css": ("Minify CSS", "Style sheets are sent with spaces and comments left in."),
    "uses-text-compression": ("Switch on compression", "Pages, scripts and styles are sent without gzip or Brotli compression."),
    "document-latency-insight": ("Make the server answer faster",
                                 "The server takes too long to send the first part of the page."),
    "cache-insight": ("Let browsers keep files longer",
                      "Returning visitors download the same files again instead of using their saved copy."),
    "font-display-insight": ("Show text while fonts load", "Text stays invisible until the web font has downloaded."),
    "legacy-javascript-insight": ("Stop sending code for old browsers",
                                  "Modern phones download extra code that only very old browsers need."),
    "duplicated-javascript-insight": ("Remove duplicate JavaScript", "The same code library is loaded more than once."),
    "third-parties-insight": ("Cut down third-party scripts",
                              "Chat widgets, trackers and embeds from other companies slow the page down."),
    "lcp-discovery-insight": ("Load the main image first",
                              "The biggest image on the first screen is found late. Preload it and do not lazy-load it."),
    "redirects": ("Avoid redirects", "The page passes through extra redirects before it starts loading."),
    "efficient-animated-content": ("Use video instead of GIFs", "Animated GIFs are many times larger than the same clip as video."),
}

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


LANGS = ("en", "bn")
_BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")


def bn_digits(value: Any) -> str:
    """12.5 -> ১২.৫"""
    return str(value).translate(_BN_DIGITS)


def nice_date(iso: str, lang: str = "en") -> str:
    """2026-11-08 -> 8 Nov 2026 (৮ নভেম্বর ২০২৬ in Bangla)"""
    try:
        y, m, d = (int(x) for x in iso[:10].split("-"))
        if lang == "bn":
            from .findings_bn import MONTHS_BN

            return bn_digits(f"{d} {MONTHS_BN[m - 1]} {y}")
        return f"{d} {MONTHS[m - 1]} {y}"
    except (ValueError, IndexError):
        return iso


def a11y_label(issue: str, lang: str = "en") -> str:
    if lang == "bn":
        from .findings_bn import A11Y_ISSUES_BN

        table = A11Y_ISSUES_BN
    else:
        table = A11Y_ISSUES
    if issue in table:
        return table[issue]
    if issue.startswith("aria-"):
        return table["aria"]
    return issue.replace("-", " ")


def speed_fix_text(fixes: list[dict[str, Any]], lang: str = "en") -> list[dict[str, Any]]:
    """[{"id", "ms"}] from the speed test -> titles, explanations and the time each would save."""
    if lang == "bn":
        from .findings_bn import SPEED_FIXES_BN as table
    else:
        table = SPEED_FIXES
    out = []
    for f in fixes or []:
        title, detail = table.get(f.get("id"), (None, None))
        if title is None:
            continue
        seconds = round(f.get("ms", 0) / 1000, 1)
        saving = f"প্রায় {bn_digits(seconds)} সেকেন্ড বাঁচবে" if lang == "bn" else f"Saves about {seconds} s"
        out.append({"id": f["id"], "title": title, "detail": detail, "seconds": seconds, "saving": saving})
    return out


class _Safe(dict):
    def __missing__(self, key: str) -> str:
        return "?"


# Evidence values that are our own words (not names from the site) and so get translated.
_WORD_KEYS = {"tester", "source", "found", "missing", "examples"}


def _fmt_values(evidence: dict[str, Any], extra: dict[str, Any], lang: str = "en") -> _Safe:
    values: dict[str, Any] = dict(extra)
    if lang == "bn":
        from .findings_bn import VALUES_BN
    else:
        VALUES_BN = {}  # noqa: N806

    def show(key: str, x: Any) -> str:
        if key == "issues":
            return a11y_label(str(x), lang)
        if lang == "bn" and isinstance(x, (int, float)) and not isinstance(x, bool):
            return bn_digits(x)
        if lang == "bn" and key in _WORD_KEYS and isinstance(x, str):
            return VALUES_BN.get(x, x)
        return str(x)

    for k, v in evidence.items():
        if isinstance(v, list):
            items = []
            for x in v:
                if isinstance(x, dict):
                    items.append(" ".join(str(x[k2]) for k2 in ("ip", "list") if k2 in x) or str(x))
                else:
                    items.append(show(k, x))
            values[f"{k}_list"] = ", ".join(items) if items else show("missing", "none")
            values[f"{k}_count"] = bn_digits(len(v)) if lang == "bn" else len(v)
            values[k] = v
        elif isinstance(v, (int, float, str)) and not isinstance(v, bool):
            values[k] = show(k, v)
        else:
            values[k] = v
    ns = len(evidence.get("nameservers", []))
    values.setdefault("ns_count", bn_digits(ns) if lang == "bn" else ns)
    if isinstance(evidence.get("expires"), str):
        values["expires"] = nice_date(evidence["expires"], lang)
    return _Safe(values)


def check_name(key: str, name: str, lang: str = "en") -> str:
    if lang == "bn":
        from .findings_bn import CHECK_NAMES_BN

        return CHECK_NAMES_BN.get(key, name)
    return name


def word(key: str, name: str, status: str, reason: str, evidence: dict[str, Any], extra: dict[str, Any],
         lang: str = "en") -> dict[str, str]:
    """The title, summary, why and fix for one result, in English ("en") or Bangla ("bn")."""
    bn = lang == "bn"
    if bn:
        from .findings_bn import FINDINGS_BN, NOT_CHECKED_BN
    if status == "not_checked":
        if bn:
            return {"title": f"{check_name(key, name, lang)}: পরীক্ষা করা হয়নি",
                    "summary": NOT_CHECKED_BN.get(reason, "এটি পরীক্ষা করা হয়নি।"),
                    "why": "", "fix": "", "offer": "none"}
        return {
            "title": f"{name}: not checked",
            "summary": NOT_CHECKED.get(reason, "This was not checked."),
            "why": "", "fix": "", "offer": "none",
        }
    entry = FINDINGS.get(key, {}).get(reason)
    if entry is None:
        return {"title": check_name(key, name, lang), "summary": "", "why": "", "fix": "", "offer": "none"}
    if bn:
        entry = {**entry, **FINDINGS_BN.get(key, {}).get(reason, {})}
    values = _fmt_values(evidence, extra, lang)
    return {k: v.format_map(values) if isinstance(v, str) else v for k, v in entry.items()}
